fn main() {
    println!("cargo:rerun-if-changed=../public/tools/Install-ShotGridNas.ps1");
    println!("cargo:rerun-if-changed=nas-public-key.xml");
    let status = std::process::Command::new("powershell.exe")
        .args(["-NoProfile", "-NonInteractive", "-Command",
            "& ([ScriptBlock]::Create([IO.File]::ReadAllText('../public/tools/Install-ShotGridNas.ps1'))) -BuildDesktop"])
        .status()
        .expect("无法启动 Windows PowerShell 编译 NAS 工具");
    assert!(status.success(), "桌面 NAS 工具编译失败");
    println!("cargo:rerun-if-changed=ShotGridUpdate.cs");
    println!("cargo:rerun-if-changed=update-public-key.xml");
    let compiler = std::path::PathBuf::from(std::env::var_os("WINDIR").unwrap())
        .join(r"Microsoft.NET\Framework64\v4.0.30319\csc.exe");
    let status = std::process::Command::new(compiler)
        .args(["/nologo", "/codepage:65001", "/target:winexe", "/out:gen/native/ShotGridUpdate.exe",
            "/resource:update-public-key.xml,release-key", "/reference:System.Web.Extensions.dll",
            "ShotGridUpdate.cs"])
        .status().expect("无法启动桌面更新工具编译器");
    assert!(status.success(), "更新工具编译失败");
    tauri_build::build()
}
