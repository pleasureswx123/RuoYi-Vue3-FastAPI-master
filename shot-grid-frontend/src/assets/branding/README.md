# 顶部影棚背景

- 文件：`cinematic-masthead.webp`，用于共用布局的品牌区和顶部栏。
- 制作方式：内置 imagegen 生成原创背景，FFmpeg 转为 WebP（质量 88）。无外链、无新增运行依赖。
- 视觉：暗色影棚、电影摄影机、琥珀光束与冷蓝轮廓光；保留橙色标志，图片不包含文字。
- 接入：`src/layout/AppLayout.vue` 的 scoped 样式引用图片，由 Vite 处理生产子路径和资源指纹。品牌区选取暖光局部，主栏保留摄影机与光束全景；小屏统一顶部高度，明暗主题下顶部保持深色与亮字。
- 原始生成提示词如下，背景不包含真实用户、项目或生产素材。

```text
Use case: stylized-concept.
Asset type: panoramic photographic background for the top navigation bar of SHOT GRID, an AI film production collaboration app. Generate the background artwork only, no UI mockup.
Primary request: an impactful, beautiful cinematic production atmosphere; sophisticated and editorial, immediately recognizable as film production.
Scene: a dark professional soundstage, a large anamorphic cinema camera with matte box in the middle-right of the composition, out-of-focus practical studio lights, subtle volumetric haze. Strong amber-gold light from the far left sweeps across the stage into cool steel-blue rim light on the camera. Rich black graphite, warm amber matching an orange brand mark, restrained blue highlights. Tangible machined-metal lens details, fine film grain, compelling depth, photoreal cinematic key art.
Composition: very wide horizontal 3:1 panorama, ideally 3072 x 1024. This will be rendered as a shallow 76px high header strip. Concentrate all recognizable visual elements within the central 25 percent of image HEIGHT, with the cinema camera lens and matte box centered around x=62%, y=50%, the camera occupying about 25% of image width. Leftmost 35% and rightmost 18% should stay comparatively dark and uncluttered so white interface text is readable above them. Long diagonal beams create energy through the middle, no overexposed white hotspots. Keep the image crisp enough to read in a very shallow crop, bold silhouette and dramatic light.
Constraints: no people, no typography, no words, no numbers, no logo, no watermark, no letterbox borders. Not a collage. Not a futuristic spaceship. Preserve clear photography and real film-production equipment.
```
