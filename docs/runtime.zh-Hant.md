# 本機執行環境

## 不需要 GPU 的展示

Python 3.11 以上即可在 repo 根目錄執行：

```powershell
python app.py
```

這條路徑只使用標準庫，讀取 package 內的四段合法中文合成音訊與先前真實 GPU 查核快照。它不下載模型、不載入 torch，也不重新推論。

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
