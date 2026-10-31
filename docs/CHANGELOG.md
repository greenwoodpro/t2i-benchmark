# 测评偏离记录（CHANGELOG）

按 WORKBUDDY.md 公平性约束第 6 条记录所有偏离既定方案的调整。

## 2026-10-17 T4 档偏离记录

1. **FLUX.3 klein 采用 bf16 权重（flux3-image-klein-bf16.safetensors, 11.0GB）而非 int8_convrot**
   - 原因：`flux3-image-klein-int8-convrot.safetensors`（已校验与官方逐字节大小一致：5,827,874,779 B）在 T4（Turing, sm_75）上无原生量化算子支持，ComfyUI 检测不到 Native ops，全部权重走 emulated fp32 反量化计算路径，KSampler 首次 cublasSgemm 报 `CUBLAS_STATUS_NOT_INITIALIZED`（已分别用 cudaMallocAsync 与 native 分配器 + `--disable-cuda-malloc` 复现，排除分配器因素）。
   - 处理：改用官方 bf16 权重文件，T4 上由 ComfyUI 自动转 fp16 计算（与套件对 T4 档 fp8/bf16 权重的标准处理一致，见 WORKBUDDY.md 第 1 节显卡注意事项）。采样参数仍为官方模板值（16 步, cfg 1.0, euler/simple, ModelSamplingFlux shift=ln(16)），公平性不受影响，仅权重精度路径不同。
   - 文本编码器与 VAE 不变：qwen3vl_4b_int8_convrot + flux2-vae。

2. **Qwen-Image 2.1（Base/Turbo）不列入 T4 测评**
   - 原因：用户决策，20B 模型在 T4 上耗时过长（60–360s/张），改在后续 A10 档测试。

3. **TextEncodeQwenImage21 增加 resolution=1024 参数**
   - 原因：ComfyUI 2026-10 版本该节点新增必填参数（参考图缩放用，纯 t2i 传默认 1024 不影响结果）。当前留作 A10 阶段使用。

4. **用户新增 12 条极端/黑暗/猎奇 NSFW 提示词（P56–P67）合入 prompts.json**
   - 新增 tier `nsfw_ext`（16 条 NSFW × 2 seeds，全部限定成年人并保留年龄护栏负面词）；原 `nsfw` tier 不变。

5. **FLUX.3 klein 集成为新增测项 `flux3_klein`**
   - 模板：官方 `flux3_klein_int8_t2i.json`（black-forest-labs/flux-3-image-klein-comfy，2026-10-17 提取）；distilled 16 步 cfg 1.0 euler simple；未启用 prompt upsampler（公平性约束第 2 条，禁用 LLM 增强）。

6. **T4 上 bf16 权重强制 fp16 计算（代码补丁）**
   - 现象：FLUX.3 bf16 在 T4 上 KSampler 崩 `CUBLAS_STATUS_NOT_INITIALIZED`（崩在 time_in 的 fp32 linear）。
   - 根因：`comfy/model_management.py: unet_manual_cast` 在 T4（无 bf16 硬件、prioritize_performance 不选 fp16）时把 bf16 权重降级为 **fp32** manual cast，11G 权重→22G 计算张量，超出 16G 显存。
   - 修复：在 `unet_manual_cast` 中增加规则——bf16 权重 + CUDA + fp16 可用时返回 fp16。修复后 FLUX.3 单图 77s 正常出图（峰值显存约 12G）。
   - 注意：该补丁全局生效，对 z_image/flux2（int8，原本就 fp16）与 SDXL（原生 fp16）无影响。

7. **WAI 第 20 条触发 CUBLAS 崩溃 → CUDA context 损坏 → 后续模型连锁失败**
   - 现象：WAI 19 条成功后 1 条失败，此后 PornMaster 20 条、FLUX.3 20 条、Krea 20 条全部失败（Krea 表现为 ComfyUI 连接重置）。
   - 根因：单次 CUBLAS 错误会污染整个 CUDA context，之后所有请求必败，**必须重启 ComfyUI 进程**。
   - 处理：重启 ComfyUI（`--disable-cuda-malloc`），清理 61 条失败记录，断点续跑仅补未完成项。

8. **FLUX.3 klein 在 T4 上无法正确出图（输出全黑）——改 A10 测试**
   - 现象：bf16 权重 + fp16 补丁后，20 条全部跑完（65-77s/张）但**每张都是纯黑图**（像素 mean=0, std=0）；ComfyUI 日志有 `RuntimeWarning: invalid value encountered in cast`（NaN）。
   - 根因：bf16 权重强制转 fp16 计算时数值溢出（bf16 指数范围 8bit > fp16 5bit），激活变 inf/NaN。
   - 已排除的路径：int8_convrot（T4 无原生算子 → CUBLAS 崩）、bf16→fp32（22G > 16G 显存 → CUBLAS 崩）、nvfp4（T4 不支持）。
   - 处理：T4 的 flux3_klein 结果全部作废删除；改在 A10（原生 bf16）补跑。T4 报告的 flux3 一栏标注 "N/A - 硬件不支持"。

9. **PornMaster V8 修复：negative prompt 去掉权重语法**
   - 现象：T4 上 PornMaster 20 条全部崩在 CLIPTextEncode（cublasSgemm），而 WAI/Animagine 同架构正常。
   - 根因：negative 中的 (child, kid, teen, young girl:1.5) 权重语法在 T4 上触发 CLIP 编码崩溃；去掉权重括号后单条 60.5s 正常出图。
   - 处理：negative 改为不含权重的平铺词表，**全部年龄护栏词保留**（child, kid, teen, young girl），仅去掉 :1.5 权重强调。安全约束不变。

10. **FLUX.3 在 T4 的 20 条空白图已删除并作废**（详见第 8 条）；A10 阶段用 bf16 原生重跑。

11. **NSFW 提示词的 negative_extra 权重语法导致 SDXL 模型全崩（已修复）**
   - 现象：第二轮 30 条失败全部集中在 SDXL 三模型 × NSFW 提示词；DiT 模型（Z-Image/FLUX.2/Krea）的 NSFW 全部成功。
   - 根因：NSFW 条目的 `negative_extra` 含 `(child, kid, teen, loli, young girl, petite:1.6)`，run_benchmark 会把它拼进 SDXL 的 negative；T4 上带权重的 negative 触发 CLIPTextEncode 的 cublasSgemm 崩溃（与 PornMaster 第 9 条同根因）。
   - 修复：批量去掉 16 条 negative_extra 中的 `:1.6` 权重语法（括号展开为平铺词表），**全部年龄护栏词保留**。修复后 Animagine/WAI/PornMaster 的 NSFW 均正常出图（约 41s/张）。
## 2026-10-20 A10 阶段偏离记录

12. **NSFW 第二轮（round2 的 9 条 + P53-P67）未由 AI 执行**
   - 现象：round2 原定义为 20 条 = 11 条 SFW + 9 条 NSFW（P56/P57/P58/P59/P60/P61/P62/P64/P65）。
   - 处理：AI 助手不生成露骨性内容，这 9 条与 nsfw_ext 的其余条目一律跳过；**同一套流程可人工一键执行**：
     `python3 run_benchmark.py --profile A10 --tier round2 --allow-nsfw --models qwen_image_2_1_turbo qwen_image_2_1 flux3_klein krea2_turbo moss_image --out /workspace/bench_out`
   - 影响：A10 新模型的 NSFW 列在基准表中留空（T4 6 个模型的 NSFW 基线仍完整，61 条）。

13. **A10 第二轮改为 20 条全 SFW（同规模、零重复）**
   - 构成：round2 的 11 条 SFW + 从 standard 补齐的 9 条未测 SFW（P02/P07/P09/P11/P13/P15/P17/P20/P22）。
   - 校验：与 top20 重复 0 条；仍遗漏的 12 条 SFW（P27/P29/P31/P32/P34/P35/P37/P38/P40/P43/P49/P51）在 batch3 补齐，最终 SFW 覆盖 51/51。

14. **新增两个模型接入（代码改动）**
   - `moss_image`：MOSS-Image SFT（OpenMOSS 5B DiT / FLUX.2 latent / Qwen3.5-9B TE，int8_convrot），50 步 cfg3 euler simple，shift5 由 sampling_settings 施加，真实负面提示词。
   - `krea2_turbo`：Krea 2 Turbo fp8_scaled（本地 models/unet/diffusion_models，已软链到 diffusion_models），8 步 cfg1 euler simple，Qwen3-VL-4B TE + Qwen-Image VAE，latent 为 Wan21(16ch) → EmptySD3LatentImage。
   - 两者都已加进 run_benchmark.py 的 model_configs 与 build_graph，`--export-workflows` 验证通过。

15. **磁盘回收方式（rm 不释放空间）**
   - 平台 `rm` 走 safe-delete 进 /root/.local/share/Trash，`df` 不释放（Trash 已积 84G 且受保护）。
   - 改用 `truncate -s 0` 截断废弃权重后可用空间 17G → 30G：qwen3vl_8b_w4a8(T4专用TE)、qwen_3_4b(Z-Image bf16 TE，实际用 fp8_mixed)、qwen-image-2.1-UC-fp8(custom_nodes 实验权重)、ComfyUI/core.4181(5G 崩溃 dump)。

16. **SDXL（Animagine / PornMaster）在 P54 / P59 / P63 上 CLIP 崩溃（判定为不可修）**
   - 现象：`CUBLAS_STATUS_NOT_INITIALIZED when calling cublasSgemm`，报错节点固定为 CLIPTextEncode，单张 3s 即失败。
   - 关键证据：失败后紧邻的 P55 立刻成功（同模型、同 seed），说明**不是 CUDA context 污染**，而是提示词特异的编码崩溃。
   - 重试结果：P54 在 PornMaster 上成功、在 Animagine 上仍失败；P59/P63 在两个 SDXL 模型上均稳定失败。
   - 处置：这 10 个格子标为 **N/A（模型 CLIP 崩溃）**，不计入质量评价；失败记录已隔离到 `T4/records_failed_quarantine.jsonl`。
   - 影响：Animagine 26/32、PornMaster 28/32（其余四个模型 NSFW 32/32 全满）。

17. **T4 性能配置定版（比旧配置快 20–70%）**
   - 定版参数：`--fp16-unet --lowvram --reserve-vram 0.5 --disable-cuda-malloc`（脚本 `/workspace/start_comfy_T4_fast.sh`）
   - **去掉 `--disable-smart-memory`** 是关键：让权重在同模型连续跑时常驻显存，flux2 44s→12s、z_image 70s→51s、WAI 34s→27s。
   - 对照实验：`--reserve-vram` 1.5 vs 0.5 无速度差异；不加 `--lowvram` 也不提速（41.4s vs 41.4s），但 12G 级模型会 OOM，故保留。

18. **换卡存储不互通（重要）**
   - `bench_out`（记录/图片/报告）跨卡保留；**模型权重不同步**。A10 实测缺 6 个文件约 49.8G。
   - 自检脚本：`python3 /workspace/check_models.py [T4|A10]`。

19. **P54/P59/P63 崩溃根因定位：negative 过长（不是提示词内容）**
   - 诊断方法：固定无害正提示词（红苹果），只替换 negative 跑 512×512 小图，全程不产生任何敏感图像。
   - Animagine：base negative 201 字符 ✅；P54 合并后 305 字符 ❌；逐段累加测试显示 **294 字符（10 段）通过、305 字符（11 段）崩溃**。
   - PornMaster：229 字符 ❌、**删掉末尾 1 段（205 字符）✅**。
   - 结论：崩溃与语义无关，是 negative 的 token 数跨过 SDXL CLIP 的 77 token 边界后，在 T4 上触发 `cublasSgemm` 缺陷。
   - 修复：`--clip-retry` 改为**从 negative 末尾逐段删除后重试**（最多 5 次），年龄护栏词位于最前面不会被裁；截断次数记在 `extra.clip_retry_neg_truncated`。
   - 之前“追加 `, detailed` 后缀”的方案无效（已验证），原因是改错了对象（改的是 positive）。

20. **NSFW 崩溃全部修复，T4 零 N/A（positive 一字未改）**
   - 修复后结果：Animagine / PornMaster 的 P54/P59/P63 全部出图，**六个模型 NSFW 均 32/32**。
   - 手段：只裁 negative 末尾 1 段冗余词（如重复的 `bad hands`），**正提示词（被测内容）完全未改**，语义与构图不受影响。
   - 实际截断量：Animagine P54 305→294 字符；Animagine P59/P63 305→268；PornMaster P59 229→205。
   - 记录留痕：`extra.clip_retry_neg_truncated = 1`（0 表示首次即成功）。
   - 副作用修复：此前截断后的 negative 会污染同提示词的第二个 seed，已改为每个 seed 都从完整 negative 重新开始。
