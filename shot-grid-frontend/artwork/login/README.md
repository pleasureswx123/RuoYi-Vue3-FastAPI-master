# 登录页 Blender 动画

## 当前版本：从分镜到交付 · 轻微环绕

当前已恢复加入上下环绕之前的四阶段展台：分镜与资产、任务与排期、版本与审核、确认与交付。保留原有轻微环绕、面板漂浮、阶段强调与移动光点，不使用大幅上下环绕或远近交替。

网页视频和封面为 `src/assets/login/production-stage.mp4`、`production-stage.webp`。视频为 12 秒、24 fps、1200×720、无声 H.264。

## 工程与重新编码

当前可编辑源工程为本目录的 `production-stage.blend`，随代码提交。中间帧位于已忽略的 `output/login-workflow/`。在仓库根目录 PowerShell 中运行（需要 Blender 5.2、FFmpeg 和 Windows 微软雅黑字体）：

```powershell
$renderDir = Join-Path (Get-Location) 'output/login-workflow'
$blender = 'D:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
& $blender --factory-startup -b shot-grid-frontend/artwork/login/production-stage.blend -o "$renderDir/frames/workflow_" -s 1 -e 288 -a
if ($LASTEXITCODE -ne 0) { throw 'Blender 渲染失败' }
ffmpeg -hide_banner -y -framerate 24 -i "$renderDir/frames/workflow_%04d.png" -vf 'crop=1200:720:0:110' -c:v libx264 -preset slow -crf 23 -pix_fmt yuv420p -movflags +faststart -an shot-grid-frontend/src/assets/login/production-stage.mp4
ffmpeg -hide_banner -y -i "$renderDir/frames/workflow_0001.png" -vf 'crop=1200:720:0:110' -frames:v 1 -quality 88 shot-grid-frontend/src/assets/login/production-stage.webp
```

本次发布仅采用此源工程，实验运镜脚本不属于发布内容。

页面保留品牌、动画、介绍三行布局，动画完整显示、不裁切、不遮挡文字。静音循环、暂停、静态封面回退和窄屏不创建视频机制保持不变。

渲染和前端检查不代表完整业务 E2E；生产发布通过仓库 `deploy/remote-deploy.ps1` 执行。
