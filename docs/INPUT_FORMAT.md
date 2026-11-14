# 输入与本地示例

严格 JSON 草稿由 `import --draft` 或 `images prepare` 使用；完整机器契约在 [schemas/import-draft.json](schemas/import-draft.json)。拒绝重复键、多余字段及数字/布尔隐式转换。所有示例为合成数据，不需要 Key。

保存一个 UTF-8 source.txt，内容为 `甲😀乙。`（末尾不要另加换行）时，它的 UTF-16 长度为5：

```json
{
  "episodeId": "ep-1",
  "kind": "video-prompts",
  "source": "source.txt",
  "offsetEncoding": "utf16",
  "segments": [{
    "id": "s1", "start": 0, "end": 5, "duration": 6.963,
    "references": [], "narration": null,
    "parameters": {"model":"MiniMax-H3","resolution":"768P","ratio":"9:16","contextIr":true,"watermark":false}
  }],
  "recipes": []
}
```

普通 import 的相对 source 以草稿文件所在目录解析；images prepare 的相对路径以故事根解析。程序只规范首BOM与换行，不去末尾换行。分段必须连续覆盖规范来源；prompt省略时取完整来源片段。video-prompts不接受改写正文；script的增强prompt必须保留原文。这里6.963秒目标保留，实际请求7秒。

加入图片时在 recipes 声明原 assetId、kind、完整prompt、exactText及dependencies；在段references按请求图序指定 `{"assetId":"hero","role":"reference_image"}`，正文可用 `{{ref:hero}}`。登记沿用该ID。first_frame只允许一张，不能与其他图或旁白混用。

旁白recipe的kind为narration，单独登记合法MP3/WAV。`narration`结构为 `{"assetId":"voice","cues":[{"start":0,"end":1}]}`，cues指向该段prompt的UTF-16位置，不能圈选角色对白或切开surrogate pair。多人或同名不同造型使用独立素材ID，不根据姓名自动重绑定。

图片交接的 request/recipe/result 全文规范与各类型模板随 Skill 打包。运行 `metasocli-py skills read metasocli-py-reference-images`，按其包内相对引用读取；手工校验使用 `python -m metasocli_py.media.handoff`。人物/场景/道具先用 `python -m metasocli_py.media.denoise compose --input … --output …` 得到最终文本，再填入同一 generationPrompt/recipes[].prompt 和文本哈希。

图片profile可只覆盖必要字段，例如 `{"boardSize":"2560x1440","firstFrameSize":"1088x1920"}`。完整支持值见 [schemas/image-profile.json](schemas/image-profile.json)。profile里的generationTimeoutMs是毫秒，默认600000，实际总等待最多1200000；300000兼容升级为600000，显式generationTimeoutMode=exact才保留300000。创建总deadline覆盖发送和接收。
