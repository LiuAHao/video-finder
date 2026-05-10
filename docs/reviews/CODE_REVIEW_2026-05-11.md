# Video Finder Code Review

Date: 2026-05-11

## Findings

### [P1] CLI 入口仍然绕过了新的输出路径安全约束

Location:

- [app/cli.py](/Users/a0000/Desktop/项目文件/video-finder/app/cli.py:280)
- [app/cli.py](/Users/a0000/Desktop/项目文件/video-finder/app/cli.py:362)
- [app/web/routes.py](/Users/a0000/Desktop/项目文件/video-finder/app/web/routes.py:175)

这次路径安全修复只接到了 Web 下载接口：`create_download_task()` 现在会通过 `build_safe_output_path()` 约束 `output_name`。但 CLI 两条下载路径仍然直接做：

```python
Path(download_dir) / output
```

也就是说，用户在 CLI 里传 `--output ../../foo.mp4` 或绝对路径时，仍然可以跳出下载目录。这样会造成：

- Web 和 CLI 行为不一致
- review 里要解决的“输出路径边界问题”实际上只修了一半
- 后续如果用户主要走 CLI，会以为这个问题已经关闭，但实际上还在

建议：

- 在 `app/cli.py` 的 `_download()` 和 `_download_direct()` 两处统一改用 `build_safe_output_path()`
- 为 CLI 加一条回归测试，验证 `--output ../../x.mp4` 最终仍落在下载目录内

### [P1] 协议相对 URL 的修复同时放宽了 JSON 配置提取，可能重新引入伪候选

Location:

- [app/services/extractor.py](/Users/a0000/Desktop/项目文件/video-finder/app/services/extractor.py:176)
- [app/services/extractor.py](/Users/a0000/Desktop/项目文件/video-finder/app/services/extractor.py:321)

为了支持 `//cdn...`，`_extract_from_json_config()` 去掉了原来的 `_is_url(value)` 预筛。现在只要 `value` 是字符串，就会先 `_normalize_url()`，再用 `_looks_like_media_resource()` 判断。

问题在于 `_looks_like_media_resource()` 里仍然保留了这个兜底：

```python
if key_hint and key_hint.lower() in self._player_config_keys:
    return True
```

这意味着像下面这种并不是真实 URL 的配置值，也可能被当成候选：

```json
{ "url": "1" }
{ "src": "auto" }
{ "file": "hd" }
```

因为这些值会先被 `urljoin()` 变成当前页面下的相对地址，然后再被 `key_hint` 放行。结果就是：

- 会把页面内普通配置文本误判成候选 URL
- 重新引入“候选里混入奇怪链接”的老问题
- 当前测试覆盖了 `//cdn...` 成功场景，但没有覆盖这种放宽后的噪声回归

建议：

- 在 `_extract_from_json_config()` 中改成“先 normalize，再要求是明确 URL 形态或明确媒体路径”
- `key_hint` 不应单独决定 `True`，至少还要满足：
  - 原值是 `http(s)://` 或 `//`
  - 或 normalize 后路径包含媒体扩展名 / 明确媒体关键词
- 增加负向测试，例如：
  - `{ "url": "1" }`
  - `{ "src": "auto" }`
  - `{ "file": "hd" }`
  这些都不应产出候选

## Validation

I ran:

- `venv/bin/python -m compileall -q app`
- `venv/bin/python -m pytest -q`

Result:

- `190 passed, 8 skipped`

当前测试整体是绿的，但上面两处问题都属于“测试还没覆盖到”的真实行为漏洞。
