# 本機執行環境

[English](runtime.en.md) | 繁體中文

## 不需要 GPU 的展示

Python 3.11 以上即可在 repo 根目錄執行：

```powershell
python app.py
```

這條路徑只使用標準庫，讀取 package 內的四段合法中文合成音訊與先前真實 GPU 查核快照。它不下載模型、不載入 torch，也不重新推論。

介面預設英文，可切換繁體中文；瀏覽器儲存可用時會記住明確選擇。語言切換不翻譯原稿、候選或 raw evidence，也不重置選段、查核者輸入或播放。

使用 `python app.py --review your-review.json` 可開啟既有 review。服務僅監聽 `127.0.0.1`，可用 `--port 8767` 改 port。每次人工決策另存至 `.local/workbench/revisions` 或 `--save-dir` 指定位置，不覆寫原 review 或音訊。重新啟動時不自動開啟上次另存修訂；需用 `--review` 明確指定。

完整 audit 會含本機來源定位資訊，分享前須檢視。來源內容變更、完整性失敗與修訂衝突會遭拒絕，不靜默修正資料。

## 選用的 GPU 環境

`pyproject.toml` 的 `gpu` extra 與 `uv.lock` 已宣告固定套件；torch 明確來自官方 CUDA 12.8 index，其他套件來自 PyPI。可在此專案自己的 `.venv` 建立環境：

```powershell
uv sync --locked --extra gpu --python 3.11
```

此命令會安裝套件，不會下載模型權重。此輪只解析 lock metadata，沒有執行此安裝命令，也沒有修改已驗證的共用 GPU 環境。新的乾淨環境與其他裝置仍需實機驗證。

已測主機使用的主要版本如下；它們不是其他裝置的相容性保證：

| 元件 | 已讀回版本 |
|---|---|
| Python | 3.11.15 |
| torch | 2.7.1+cu128 |
| transformers | 4.57.6 |
| tokenizers | 0.22.2 |
| numpy | 2.3.5 |
| huggingface-hub | 0.36.0 |
| safetensors | 0.7.0 |

GPU adapter 只接受 CUDA，不會靜默回退 CPU。Whisper 使用 float16；Phi 動作 policy 使用 bfloat16 與原生 SDPA。需由裝置實測記憶體、runtime 與品質，不以套件安裝成功代替功能驗收。

## 模型來源與本機權重

- 語音工具：[OpenAI Whisper medium](https://huggingface.co/openai/whisper-medium)，目前已驗 snapshot revision `abdf7c39ab9d0397620ccaea8974cc764cd0953e`。
- 動作 policy：[Microsoft Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct)，adapter 固定 revision `cfbefacb99257ffa30c83adab238a50856ac3083`，並核對兩個官方權重 shard 的 SHA256。
- 兩個 adapter 皆只讀取明確提供的本機權重，使用 `local_files_only=True`。不使用遠端自訂 model code，也不自動下載或替換模型。
- Phi 只從受限動作與既有工具證據選擇，不產生可直接接受的新逐字稿；候選仍需人工決定。

使用實際模型目錄設定自己的 `WHISPER_MODEL` 與 `PHI_MODEL` 環境變數，再以 GPU 環境的 Python 執行：

```powershell
python app.py --input your-input.json --whisper-model "$env:WHISPER_MODEL" --agent-model "$env:PHI_MODEL" --policy agent
```

開啟畫面仍不會載入模型；按「執行查核」才啟動有界背景工作。未設定 tool／model 的展示不顯示執行按鈕。若 runtime、權重、工具或 policy 失敗，介面顯示錯誤並保留上一份結果，不冒充完成。

目前語音工具要求 mono、16 kHz、PCM16 WAV，單次音訊區間最多 30 秒。缺少時碼、其他格式與更長區間需要明確的轉接流程。主機 GPU 的 Whisper medium 結果不代表 UGen300 USB 上 Whisper Small 已相容；尚未進行 USB 實測。

## 輸入契約與 CLI

輸入 JSON 包含相對的 `source.path`、有限正值秒數 `source.duration`，以及具有唯一 `id`、有限 `start`／`end`、原始 `text` 的 segments。speaker 等 metadata 可保留。缺時碼須先對齊；時間缺口與重疊只是查核線索，不是漏句或錯誤的證明。

純虛構 fixture 的 CLI 決策與匯出範例見 [繁中 README](../README.zh-Hant.md#進一步使用)。它使用靜音音訊與標明虛構的 evidence，只驗證流程，不冒充語音辨識。輸出拒絕覆寫既有檔案，重跑須使用新位置。

從 repo 根目錄執行工程驗證：

```powershell
$env:PYTHONPATH = "$PWD/src"
python -B -m unittest discover -s tests -v
node tests/test_workbench_js.mjs
```

已記錄的執行與限制見 [validation（英文）](validation.md)。工程驗證、模型推論、瀏覽器操作與獨立人工品質接受分開核對。
