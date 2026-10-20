from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parent / "checkpoints"
BASE_DIR = ROOT / "Wan2.1-T2V-1.3B"
LORA_DIR = ROOT / "CineTrans-DiT"


def main():
    base_path = snapshot_download(
        repo_id="Wan-AI/Wan2.1-T2V-1.3B",
        local_dir=str(BASE_DIR),
        allow_patterns=[
            "config.json",
            "diffusion_pytorch_model.safetensors",
            "models_t5_umt5-xxl-enc-bf16.pth",
            "Wan2.1_VAE.pth",
            "google/umt5-xxl/*",
        ],
        token=False,
    )
    lora_path = snapshot_download(
        repo_id="NumlockUknowSth/CineTrans-DiT",
        local_dir=str(LORA_DIR),
        allow_patterns=["weights.pt"],
        token=False,
    )
    print(f"base_path={base_path}")
    print(f"lora_path={lora_path}")


if __name__ == "__main__":
    main()
