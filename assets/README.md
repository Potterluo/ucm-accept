# 离线资产目录（构建时填充）

此目录不随源码提交业务数据。离线构建时请把以下物料放到固定路径，并生成 `manifest.json`：

```text
assets/
├── evalscope-cache/          # EvalScope 数据集缓存（EVALSCOPE_CACHE）
├── modelscope-cache/         # ModelScope 缓存（MODELSCOPE_CACHE）
├── tokenizers/
│   └── Qwen2.5-0.5B-Instruct/
├── manifest.json             # scripts/prepare_assets.py 生成
└── README.md
```

构建校验：

```bash
python scripts/prepare_assets.py --assets-dir assets --output assets/manifest.json
python scripts/prepare_assets.py --assets-dir assets --check
ucm-accept --doctor
```

`config.offline.yaml` 默认引用 `/opt/ucm-accept/assets/tokenizers/Qwen2.5-0.5B-Instruct`。
