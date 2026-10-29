# 可攜式中文合成示範

`source.wav` 是 Windows SAPI 朗讀作者撰寫的四段虛構中文內容，共 27.3775 秒；沒有病人、合作影片或臨床評估題目。

`review.json` 保存一次真實的 Microsoft Phi-4-mini-instruct 與 OpenAI Whisper medium 本機 CUDA 執行紀錄，原樣保留模型使用的繁簡、標點、重複與數字。初稿含手動植入錯誤；其中亦有對照段落，不能把四段結果當成自然 ASR 錯誤率或人工品質驗收。朗讀腳本是合成來源，不是獨立人工 ground truth，也沒有送入 policy。

這次執行有 8 次 LLM 決策與 4 次語音工具呼叫：兩段選出候選並保持 pending，兩段因 Phi 回覆 Markdown code fence 被嚴格 parser 拒絕，明確標為 needs_human_review。原始失敗 trace 保留，沒有修飾成成功；這不是準確率或省工率。預設選段 s3，用來展示手動漏句初稿與工具候選的差異。

這是既有 GPU 查核快照。啟動無 GPU 工作台時只載入資料與音訊，不會重新推論或下載模型。portable manifest 不含私人絕對路徑；本地 server 會在啟動時解析 package 內的單一音訊，檢查 hash，再建立本機 source locator。公開精簡的 agent 與固定流程對照另存於 `docs/results/`。

人工決策只另存至使用者指定的修訂目錄，不會改寫此快照或音訊。下載的完整 audit 會含本機 source locator，應留在私人環境。
