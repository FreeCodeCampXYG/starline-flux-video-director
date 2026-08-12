# 七张共享边界帧导演提示词

这 7 张图必须保持同一人物、服装、工作室和灯位。最稳的制作方式是先生成 `frame-00`，后续每张都把上一张作为身份与场景参考进行编辑/衍生；不要独立文生图七次。

## 全局锁定词

```text
Photorealistic cinematic technology documentary, the exact same Chinese male independent developer in his early thirties, short black hair, plain dark charcoal shirt, natural realistic face and hands, the exact same quiet modern home studio at night, deep-indigo ambient light, one warm-gold desk lamp behind him on camera-left, 35mm lens, controlled contrast, premium commercial cinematography, restrained and believable, 16:9 landscape, no readable text, no letters, no logos, no watermark, no cyberpunk neon, no duplicate person, no malformed hands, no distorted screen.
```

## frame-00｜情境开场

```text
[GLOBAL LOCK] Medium three-quarter shot. The developer sits at his desk with only three translucent abstract AI answer cards floating around the monitor. Calm focused expression, hands naturally resting near the keyboard. The room is orderly and quiet. Composition keeps the developer center-left and preserves right-side depth. This is a clean opening frame with stable geometry.
```

## frame-01｜情境收束 / 任务开场

```text
[Use frame-00 as strict identity, clothing, set, geometry and lighting reference.] Change only the event state: many translucent abstract answer cards now surround the developer but remain visually controlled; nearest cards are softly out of focus. One warm-gold abstract question-shaped light is sharp at the center of his gaze. The camera is slightly closer on the same axis. Preserve every other invariant.
```

## frame-02｜任务收束 / 方法开场

```text
[Use frame-01 as strict reference.] The same cards have settled onto the same desk as abstract presentation pages, transcript sheets, video timeline tiles and code fragments, all without readable text. A thin warm-gold path connects them into one clean task map. Three-quarter top-down view reached from the same camera side. Same person, face, clothing, room and lamp.
```

## frame-03｜方法收束 / 验收开场

```text
[Use frame-02 as strict reference.] The task map has unfolded into three elegant concentric planning rings and a compact modular workflow. The developer is clearly the single human director at the center; four small abstract light agents form a clockwise research-organize-verify-publish pattern. Same desk layout, same identity and same lighting. No text.
```

## frame-04｜验收收束 / 构建开场

```text
[Use frame-03 as strict reference.] A single refined digital artifact sits above the workflow, surrounded by four restrained warm-gold scanning rings. All checked nodes are calm green and geometrically stable. The developer watches from the same relationship with a subtle expression of approval. Preserve face, hands, clothes, room and camera side.
```

## frame-05｜构建收束 / 结果开场

```text
[Use frame-04 as strict reference.] Modular code blocks have assembled into a compact creator toolkit on the desk. Three polished abstract artifact cards hover above it: a visual learning webpage, a reusable workflow module, and a source-grounded study website, using layout shapes only with no readable words. A warm-gold pulse links all three. Same developer and studio.
```

## frame-06｜最终收尾

```text
[Use frame-05 as strict reference.] Wide final composition. The three artifact cards have expanded into an elegant constellation of many small learning-page thumbnails and three major open-source project nodes. The same developer remains at the real desk, calmly closing a plain notebook. Warm-gold pathways continue softly behind him. Deep-indigo shadows, earned quiet confidence, generous clean negative space on the right for later Chinese title and GitHub attribution. No generated text or logos.
```

