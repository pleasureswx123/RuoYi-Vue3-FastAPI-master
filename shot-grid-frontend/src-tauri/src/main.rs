#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::collections::HashSet;
use std::sync::atomic::{AtomicUsize, Ordering};
use tauri::{
    webview::NewWindowResponse, AppHandle, AssetResolver, Url, WebviewUrl, WebviewWindowBuilder,
    Wry,
};
use webview2_com::{
    take_pwstr, LaunchingExternalUriSchemeEventHandler,
    Microsoft::Web::WebView2::Win32::{ICoreWebView2_18, COREWEBVIEW2_WEB_RESOURCE_CONTEXT_ALL},
    WebResourceRequestedEventHandler,
};
use windows::{
    core::{Interface, HSTRING, PWSTR},
    Win32::UI::{
        Shell::SHCreateMemStream,
        WindowsAndMessaging::{MessageBoxW, MB_ICONERROR},
    },
};

const ORIGIN: &str = "http://192.168.10.122:12581";
const APP_PATH: &str = "/shot-grid-app/";
static NEXT_WINDOW: AtomicUsize = AtomicUsize::new(1);

fn check_update(app: AppHandle, manual: bool) {
    std::thread::spawn(move || {
        let result = std::env::current_exe().and_then(|exe| {
            std::process::Command::new(exe.with_file_name("tools").join("ShotGridUpdate.exe"))
                .arg(app.package_info().version.to_string())
                .arg(if manual { "manual" } else { "startup" })
                .status()
        });
        match result {
            Ok(status) if status.code() == Some(42) => app.exit(0),
            Err(_) if manual => show_error("无法启动桌面更新工具，请重新安装桌面端。"),
            _ => {}
        }
    });
}

fn frontend_path(url: &Url) -> Option<&str> {
    if url.origin().ascii_serialization() != ORIGIN
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return None;
    }
    url.path().strip_prefix(APP_PATH)
}

fn show_error(message: &str) {
    unsafe {
        let _ = MessageBoxW(
            None,
            &HSTRING::from(message),
            &HSTRING::from("Shot Grid 制作工作台"),
            MB_ICONERROR,
        );
    }
}

fn load_frontend(
    view: tauri::webview::PlatformWebview,
    assets: AssetResolver<Wry>,
    start: &Url,
) -> windows::core::Result<()> {
    // 仅从安装包提供制作平台页面。API、媒体 Range 和 WebSocket 走公司原有同域网关。
    unsafe {
        let browser = view.controller().CoreWebView2()?;
        // 在 WebView2 弹出外部应用确认前接管请求，只运行安装包内的固定验签工具。
        let external = browser.cast::<ICoreWebView2_18>()?;
        let mut external_token = 0;
        external.add_LaunchingExternalUriScheme(
            &LaunchingExternalUriSchemeEventHandler::create(Box::new(|_, event| {
                let Some(event) = event else { return Ok(()) };
                event.SetCancel(true)?;
                let mut origin = PWSTR::null();
                event.InitiatingOrigin(&mut origin)?;
                if take_pwstr(origin).trim_end_matches('/') != ORIGIN {
                    return Ok(());
                }
                let mut uri = PWSTR::null();
                event.Uri(&mut uri)?;
                let uri = take_pwstr(uri);
                if !uri.starts_with("shotgrid-nas://open-v1/") || uri.len() > 14000 {
                    return Ok(());
                }
                let launched = std::env::current_exe().and_then(|exe| {
                    std::process::Command::new(exe.with_file_name("tools").join("ShotGridNas.exe"))
                        .arg(uri)
                        .spawn()
                });
                if launched.is_err() {
                    show_error("无法启动安装包内的 NAS 工具，请重新安装桌面端。");
                }
                Ok(())
            })),
            &mut external_token,
        )?;
        let environment = view.environment();
        browser.AddWebResourceRequestedFilter(
            &HSTRING::from(format!("{ORIGIN}{APP_PATH}*")),
            COREWEBVIEW2_WEB_RESOURCE_CONTEXT_ALL,
        )?;
        let mut token = 0;
        let files: HashSet<_> = assets.iter().map(|(key, _)| key.into_owned()).collect();
        let handler = WebResourceRequestedEventHandler::create(Box::new(move |_, event| {
            let Some(event) = event else { return Ok(()) };
            let mut uri = PWSTR::null();
            event.Request()?.Uri(&mut uri)?;
            let Ok(url) = Url::parse(&take_pwstr(uri)) else {
                return Ok(());
            };
            let Some(path) = frontend_path(&url) else {
                return Ok(());
            };
            // 刷新业务路由时返回首页，缺失的静态资源保留 404。
            let file = if path.rsplit('/').next().unwrap_or("").contains('.') {
                format!("/{path}")
            } else {
                "/index.html".to_owned()
            };
            let asset = files
                .contains(&file)
                .then(|| assets.get(file.clone()))
                .flatten();
            let (status, reason, mime, stream) = match asset {
                Some(asset) => {
                    // NAS 安装模板按文本读取，以便在下载时绑定服务端公钥。
                    let mime = if file.ends_with(".ps1") {
                        "text/plain; charset=utf-8".into()
                    } else {
                        asset.mime_type
                    };
                    (200, "OK", mime, SHCreateMemStream(Some(&asset.bytes)))
                }
                None => (404, "Not Found", "text/plain".to_owned(), None),
            };
            let headers = HSTRING::from(format!("Content-Type: {mime}\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff"));
            let response = environment.CreateWebResourceResponse(
                stream.as_ref(),
                status,
                &HSTRING::from(reason),
                &headers,
            )?;
            event.SetResponse(&response)
        }));
        browser.add_WebResourceRequested(&handler, &mut token)?;
        browser.Navigate(&HSTRING::from(start.as_str()))
    }
}

fn open_window(app: &AppHandle, label: String, start: Url) -> tauri::Result<()> {
    let assets = app.asset_resolver();
    let handle = app.clone();
    let update_handle = app.clone();
    let window = WebviewWindowBuilder::new(
        app,
        label,
        WebviewUrl::External("about:blank".parse().unwrap()),
    )
    .initialization_script(format!("Object.defineProperties(window, {{__SHOTGRID_DESKTOP__: {{value:true}}, __SHOTGRID_VERSION__: {{value:'{}'}}}});", app.package_info().version))
    .title("Shot Grid 制作工作台")
    .inner_size(1360.0, 860.0)
    .min_inner_size(900.0, 600.0)
    .disable_drag_drop_handler()
    .on_navigation(move |url| {
        if url.origin().ascii_serialization() == ORIGIN && url.path() == "/desktop-updates/check" {
            check_update(update_handle.clone(), true);
            return false;
        }
        url.as_str() == "about:blank"
            || frontend_path(url).is_some()
            || url.scheme() == "shotgrid-nas" && url.host_str() == Some("open-v1")
            || url.as_str().starts_with(&format!("blob:{ORIGIN}/"))
    })
    .on_new_window(move |url, _| {
        if frontend_path(&url).is_some() {
            let app = handle.clone();
            tauri::async_runtime::spawn(async move {
                let label = format!("detail-{}", NEXT_WINDOW.fetch_add(1, Ordering::Relaxed));
                if let Err(err) = open_window(&app, label, url) {
                    show_error(&format!("打开页面失败：{err}"));
                }
            });
        }
        NewWindowResponse::Deny
    })
    .build()?;
    window.with_webview(move |view| {
        if let Err(err) = load_frontend(view, assets, &start) {
            show_error(&format!("加载内置制作平台失败：{err}"));
        }
    })
}

fn main() {
    if let Err(err) = tauri::Builder::default()
        .setup(|app| {
            open_window(
                app.handle(),
                "main".into(),
                format!("{ORIGIN}{APP_PATH}workbench").parse()?,
            )?;
            check_update(app.handle().clone(), false);
            Ok(())
        })
        .run(tauri::generate_context!())
    {
        show_error(&format!("工作台启动失败：{err}"));
    }
}
