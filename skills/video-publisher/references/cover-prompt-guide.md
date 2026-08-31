# 封面提示词指南（Cover Prompt Guide）

> **何时加载：** 物料数据生成步骤（generate_material.py 封面文生图）中
> 编写/完善 `project_config.yaml` 的 `cover.prompt` 时。
> 目的：让封面**带上与主题相关、吸引点击的文字**，而非纯视觉图。

## 为什么封面要带文字

视频封面是用户点击的入口，带主题文字的封面显著提升点击率：
- 文字直接传达视频主题（观众扫一眼就知道讲什么）；
- 文字内容来自物料上下文：`{title}` / `{topic}`（explainer-video-maker 联动
  时 `topic` 是最佳文字来源，见 explainer-video-maker-integration.md）；
- 注意文字要**短**：封面文字 2-12 字为宜（如"GPU架构详解"、"AI 70年"），
  长标题在封面小图上会糊。agent 应从 `{topic}`/`{title}` 中提炼短关键词
  用于封面文字，而非整句照搬。

## 文字嵌入专用模板

**当你需要在图像中包含可读文字时，务必使用明确的语言描述内容、字体风格
和排版位置。**

- 举例：画面中央有一个发光的LED屏幕，上面显示'Hello World'和'你好世界'，
  中英文并列，无衬线字体，蓝色渐变背景
- 小贴士：使用 "displaying"、"written on"、"engraved with" 等动词明确指出
  文字存在形式
- 小贴士：指定字体类型（如 serif, sans-serif, calligraphy）有助于提升一致性

### 提示词写法示例

```yaml
cover:
  # 中文平台（B站/抖音/视频号）：文字用中文，明确载体/位置/字体
  prompt: "科技感视频封面，画面中央发光LED屏幕 displaying 'GPU架构详解'，
           无衬线字体（sans-serif），深蓝渐变背景配电路纹理，
           金属质感、专业高清，文字清晰可读"
  # 英文平台（youtube）：displaying 动词 + 字体 + 排版位置
  # prompt: "Tech video thumbnail, a glowing LED screen in the center displaying
  #          'GPU Architecture Explained', sans-serif bold font, dark blue gradient
  #          background with circuit patterns, high contrast, readable text"
```

**推荐结构**（按文字嵌入模板组织）：`主题视觉元素 + 文字载体动词（displaying/
written on）+ 文字内容 + 字体类型 + 排版位置 + 背景/风格 + 清晰度要求`。

## 平台封面规格与文字安全区

| 平台 | 规格 | 文字排版建议 |
|------|------|-------------|
| B站 | 3:2（1600x1000） | 标题文字居上 1/3，避免被平台角标遮挡 |
| 抖音 | 3:4 竖版（1080x1440） | 文字居上，下方留空间给右侧 UI 遮挡 |
| 微信视频号 | 9:16（1080x1920） | 文字居上 1/4，底部 1/3 避免被遮挡 |
| youtube | 16:9（1280x720） | 文字偏左，右侧留给时长条/进度条 |

具体规格以 `platform_config.yaml` 的 `cover_spec`（platform-integration.md）
与各平台发布页要求为准；`generate_material.py` 按项目 `cover.width/height`
生成。

## 负面提示词建议

```yaml
negative_prompt: "文字水印，模糊，低质量，文字变形，乱码，多语言文字混杂，手写体潦草"
```

- 文字类负面词（文字变形/乱码/模糊）有助于提升文字可读性；
- 长文字易触发模型乱码——再次强调：封面文字保持 2-12 字短关键词。

## agent 检查清单（生成/审核封面时）

1. 封面是否包含与主题相关的文字（而非纯视觉）？文字是否 ≤12 字？
2. 提示词是否用 displaying/written on 等动词明确文字载体与位置？
3. 是否指定字体类型（sans-serif 等）？
4. 文字排版位置是否符合平台安全区（cover_spec）？
5. 手动模式审核时，把封面截图展示给用户确认文字可读性。
