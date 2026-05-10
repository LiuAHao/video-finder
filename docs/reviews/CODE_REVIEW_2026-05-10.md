# Video Finder Code Review

Date: 2026-05-10

Scope reviewed:

- `app/services/extractor.py`
- `app/services/sniffer.py`
- `app/web/routes.py`
- Related tests in `tests/`

## Findings

### [P1] HLS `.ts` 分片会从响应监听重新混进候选列表

Location: [app/services/sniffer.py](/Users/a0000/Desktop/项目文件/video-finder/app/services/sniffer.py:210), [app/services/sniffer.py](/Users/a0000/Desktop/项目文件/video-finder/app/services/sniffer.py:217)

`_on_request()` 已经会过滤 HLS `.ts` 分片，但 `_on_response()` 只要看到 `content-type` 命中 `VIDEO_CONTENT_TYPES` 就会把响应补回 `_network_resources`。由于常见 HLS 分片响应是 `video/MP2T`，这会把之前已经排除掉的 `.ts` 分片重新加入候选池。

结果是：

- 候选列表可能重新出现大量 HLS 分片 URL
- 排序和“推荐资源”可能被噪声干扰
- 用户可能误点到单个分片而不是播放清单

建议：

- 在 `_on_response()` 中复用 `_is_hls_segment(url)` 过滤
- 或者显式只接受 manifest / 直链视频，而不是所有 `video/*` 响应
- 补一条集成测试，覆盖“请求被过滤但响应又被加入”的场景

### [P1] 当前“集数相关性”规则会误删合法视频资源

Location: [app/services/extractor.py](/Users/a0000/Desktop/项目文件/video-finder/app/services/extractor.py:391), [app/services/extractor.py](/Users/a0000/Desktop/项目文件/video-finder/app/services/extractor.py:413)

`_extract_candidate_episode_hint()` 会把文件名尾部的任意 1-3 位数字都当成集数，例如：

- `video_720.mp4`
- `source_1080.m3u8`
- `cdn_001.mp4`

如果页面 URL 被识别成“第 1 集”，这些资源会因为 `720 != 1`、`1080 != 1`、`001 == 1/或不稳定` 被 `_is_relevant_to_page()` 直接过滤或影响评分。

这会误伤很多真实资源，因为很多站点把清晰度、码率、内部资源编号放在文件名末尾，并不表示集数。

建议：

- 只有命中强语义模式时才提取集数，例如 `ep01`、`episode-01`、`第01集`
- 不要把裸尾号 `01`、`720`、`1080` 默认当成集数
- 至少把“直接过滤”降级为“排序惩罚”，避免把真实资源从结果里彻底删掉

### [P2] `output_name` 没有限制路径逃逸，用户可写出下载目录之外

Location: [app/web/routes.py](/Users/a0000/Desktop/项目文件/video-finder/app/web/routes.py:172)

下载接口里对 `request.output_name` 直接执行：

```python
output_path = str(Path(download_dir) / request.output_name)
```

如果传入绝对路径或 `../`，结果会跳出配置的下载目录。例如：

- `/tmp/out.mp4`
- `../../Desktop/test.mp4`

对于本地工具来说这不一定是恶意输入，但它会让“下载目录配置”失去约束，也容易把文件落到意外位置。

建议：

- 对 `output_name` 只保留 basename
- 拒绝绝对路径和 `..` 路径段
- 最终对解析后的路径执行 `resolve()`，确认仍位于 `download_dir` 之下

### [P2] JSON 配置里的协议相对 URL 会被漏抓

Location: [app/services/extractor.py](/Users/a0000/Desktop/项目文件/video-finder/app/services/extractor.py:177)

`_extract_from_json_config()` 在进入 `_normalize_url()` 之前，先要求：

```python
self._is_url(value)
```

而 `_is_url()` 只接受 `http://` / `https://`。这意味着像下面这种常见配置不会被提取：

```json
{
  "src": "//cdn.example.com/video.m3u8"
}
```

但 `_normalize_url()` 其实已经支持把 `//` 规范化为 `https:`，所以这里是一个前置校验把合法资源挡掉了。

建议：

- 去掉这层 `_is_url(value)` 预筛
- 改成先 `_normalize_url()`，再判断是否像媒体资源

## Open Questions / Assumptions

- 本次 review 主要关注“候选发现与下载入口”的正确性，没有深入审查前端视觉层和历史记录 UI。
- 我默认目标是“尽量发现真实视频资源，同时尽量少把无关文件放进候选列表”，不是做站点级定制适配。
- 我没有针对真实外部站点做大规模回归，只依据当前实现、测试和静态逻辑审查。

## Change Summary

当前版本的整体方向是对的，模块边界也比较清楚：Playwright 网络监听、HTML 静态提取、候选排序、下载调度、Web/CLI 双入口都已经成型。主要风险不在“有没有功能”，而在一些启发式规则过强或不对称：

- 一边在请求层过滤噪声，另一边又在响应层把噪声加回来
- 一边想用“集数相关性”降噪，一边又把很多普通数字误当成集数
- 下载入口缺少路径边界约束
- 某些合法 URL 形式被前置校验直接漏掉

优先建议修 P1 两项，再补 P2，之后再做一轮真实页面回归，会比较稳。
