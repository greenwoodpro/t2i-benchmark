#!/usr/bin/env bash
# =====================================================================
#  setup_comfyui.sh —— 在 Cloud Studio 终端中安装 ComfyUI（CPU 机器也可执行，只装环境不跑图）
#
#  用法:  bash setup_comfyui.sh [安装目录，默认 $PWD/ComfyUI]
#  环境变量:
#    PIP_INDEX_URL  pip 镜像（国内可设 https://pypi.tuna.tsinghua.edu.cn/simple）
#    TORCH_INDEX    PyTorch wheel 源，默认 https://download.pytorch.org/whl/cu124
#    SKIP_TORCH=1   已有可用 torch 时跳过
#
#  说明:
#   * Z-Image / FLUX.2 klein / Qwen-Image 2.1 / int8_convrot 量化格式都要求较新的 ComfyUI，
#     本脚本始终 clone 最新 master；已存在目录则 git pull。
#   * T4 (Turing, sm_75) 与 A10 (Ampere, sm_86) 在 cu121/cu124 的 torch wheel 都可用。
#     若 Cloud Studio 镜像已自带 torch+cuda，设 SKIP_TORCH=1。
# =====================================================================
set -euo pipefail
DIR="${1:-$PWD/ComfyUI}"
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cu124}"

echo "== 系统信息"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv 2>/dev/null || echo "无 GPU（CPU 机器，仅做下载/安装）"
python3 --version; free -g | head -2; df -h . | tail -1

echo "== 系统工具"
command -v aria2c >/dev/null 2>&1 || (sudo apt-get update -qq && sudo apt-get install -y -qq aria2 git) || true

if [[ -d "$DIR/.git" ]]; then
  echo "== 更新 ComfyUI"; git -C "$DIR" pull --ff-only
else
  echo "== 克隆 ComfyUI"; git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "$DIR"
fi

echo "== Python 虚拟环境"
python3 -m venv "$DIR/venv"
# shellcheck disable=SC1091
source "$DIR/venv/bin/activate"
pip install -q -U pip wheel

if [[ "${SKIP_TORCH:-0}" != "1" ]]; then
  echo "== 安装 PyTorch ($TORCH_INDEX)"
  pip install -q torch torchvision torchaudio --index-url "$TORCH_INDEX"
fi
echo "== 安装 ComfyUI 依赖"
pip install -q -r "$DIR/requirements.txt"
pip install -q requests pillow

echo "== ComfyUI-Manager（可选，方便补节点）"
[[ -d "$DIR/custom_nodes/ComfyUI-Manager" ]] || git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager.git "$DIR/custom_nodes/ComfyUI-Manager"

cat > "$DIR/start_T4.sh" <<EOF
#!/usr/bin/env bash
# T4 16G：fp16 计算 + 低显存模式；--reserve-vram 给文本编码器留余量
cd "$DIR" && source venv/bin/activate && \\
python main.py --listen 0.0.0.0 --port 8188 --fp16-unet --lowvram --reserve-vram 1.5 --disable-smart-memory "\$@"
EOF
cat > "$DIR/start_A10.sh" <<EOF
#!/usr/bin/env bash
# A10 24G：默认 bf16；仅在 9B / Qwen 爆显存时追加 --normalvram 或 --lowvram
cd "$DIR" && source venv/bin/activate && \\
python main.py --listen 0.0.0.0 --port 8188 --bf16-unet "\$@"
EOF
chmod +x "$DIR/start_T4.sh" "$DIR/start_A10.sh"

python - <<'EOF'
import torch
print("torch", torch.__version__, "cuda", torch.version.cuda, "available", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu", torch.cuda.get_device_name(0), "bf16 support", torch.cuda.is_bf16_supported())
EOF
echo "== 完成。启动:  bash $DIR/start_T4.sh   或   bash $DIR/start_A10.sh   （后台: nohup bash $DIR/start_A10.sh > comfy.log 2>&1 &）"
