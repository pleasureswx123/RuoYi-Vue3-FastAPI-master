fn main() {
    println!("cargo:rerun-if-changed=../public/tools/Install-ShotGridNas.ps1");
    println!("cargo:rerun-if-changed=nas-public-key.xml");
    let status = std::process::Command::new("powershell.exe")
        .args(["-NoProfile", "-NonInteractive", "-Command",
            "& ([ScriptBlock]::Create([IO.File]::ReadAllText('../public/tools/Install-ShotGridNas.ps1'))) -BuildDesktop"])
        .status()
        .expect("无法启动 Windows PowerShell 编译 NAS 工具");
    assert!(status.success(), "桌面 NAS 工具编译失败");
    tauri_build::build()
}
