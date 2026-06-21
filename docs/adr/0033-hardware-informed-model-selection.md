# ADR-0033: Hardware-Informed Model Selection

## Status
**Accepted** — June 2026

## Context

ADR-0025 established the three-profile model strategy (fast / balanced / quality) with Qwen 2.5 variants as the primary model family, validated against a single machine (MacBook Pro M4, 48 GB unified memory). ADR-0032 formalised the two-machine deployment reality: a macOS MBP and a Windows laptop, each with meaningfully different hardware.

No hardware analysis had been performed against the **Windows laptop** to verify whether the chosen models were appropriate for its constraints, and the macOS models had not been revisited since the M4 evaluation. The result was a single set of model profiles applied uniformly to both hosts, despite one having 36 GB unified memory (macOS M3 Pro) and the other having a discrete 16 GB VRAM GPU (Windows RTX 4090 Laptop).

### LLMfit Analysis

LLMfit (container `ghcr.io/alexsjones/llmfit`) was run on both hosts to evaluate hardware fit, estimated throughput, and recommended models. Live Ollama benchmarks (`llmfit bench`) were also run on Windows to capture real inference tok/s.

**Reports saved to:** OneDrive Desktop — `report.html` (macOS), `report-windows.html` (Windows)

### Key Findings

**Windows (RTX 4090 Laptop, 16 GB VRAM, 32 GB RAM, i9-13980HX):**

| Model           | Fit      | VRAM Used | Actual tok/s | LLMfit Score |
|-----------------|----------|-----------|--------------|--------------|
| mistral:7b      | Perfect  | 9.1 GB    | 98.3         | 78.8         |
| llama3.1:8b     | Perfect  | 9.9 GB    | 92.1         | 79.4         |
| qwen2.5:14b     | Perfect  | 13.8 GB   | 50.5         | 68.5         |
| qwen3:14b       | Perfect  | 13.6 GB   | 49.7         | 72.2         |
| deepseek-r1:14b | Perfect  | 13.8 GB   | 51.2         | 84.9         |
| qwen2.5:32b     | Marginal | 14.6 GB   | not installed | 59.0        |

`qwen2.5:32b` requires a minimum of 16.8 GB VRAM at Q4_K_M; with only 16 GB available it can only run at Q2_K (the lossiest available quantisation), giving a score of 59.0 — the lowest of any installed model. It is not viable as the quality profile on this hardware.

**macOS (M3 Pro, 36 GB unified memory):**

Unified memory means VRAM and RAM are shared. Models up to ~30 GB fit comfortably. The MoE architecture of Qwen3.6-35B-A3B (active parameters ~3B, total 36B) loads all experts in unified memory and is Perfect fit through 128K context. Model tags on macOS to be confirmed during implementation (Issue #318).

---

## Decision

### 1. Add `device_profiles` to `model_config.json`

Introduce a `device_profiles` top-level block (config version bumped to `"2.1"`) mapping platform key → profile name → Ollama model tag:

```json
"device_profiles": {
  "windows": {
    "fast":     "llama3.1:8b",
    "balanced": "qwen3:14b",
    "quality":  "deepseek-r1:14b"
  },
  "darwin": {
    "fast":     "qwen3:4b",
    "balanced": "qwen3:14b",
    "quality":  "qwen3.6:35b"
  }
}
```

macOS model tags are subject to confirmation during Issue #318 (MBP verification). If `qwen3.6:35b` is not available as an Ollama tag, `qwen3:14b` serves as the quality fallback on macOS.

### 2. Model assignments

| Platform | Profile  | Previous model  | New model           |
|----------|----------|-----------------|---------------------|
| Windows  | fast     | mistral:7b      | llama3.1:8b         |
| Windows  | balanced | qwen2.5:14b     | qwen3:14b           |
| Windows  | quality  | qwen2.5:32b     | deepseek-r1:14b     |
| macOS    | fast     | mistral:7b      | qwen3:4b (TBC)      |
| macOS    | balanced | qwen2.5:14b     | qwen3:14b           |
| macOS    | quality  | qwen2.5:32b     | qwen3.6:35b (TBC)   |

Rationale per Windows change:
- **fast:** `llama3.1:8b` outscores `mistral:7b` (79.4 vs 78.8), with better quality (83 vs 76) and 1M token context vs 32K at comparable speed (92 vs 98 tok/s).
- **balanced:** `qwen3:14b` is a newer generation than `qwen2.5:14b`, scores higher (72.2 vs 68.5), and fits the same VRAM footprint.
- **quality:** `deepseek-r1:14b` is the highest-scoring installed model (84.9) and fits comfortably in 16 GB VRAM. `qwen2.5:32b` is physically marginal and only viable at Q2_K.

### 3. Device-aware model resolution in `SettingsService`

`SettingsService.get_active_model()` (`app/settings.py`) is extended with an additional resolution step:

1. `model_override` from `settings.json` — highest precedence, unchanged
2. `device_profiles[platform_key][active_profile]` from `model_config.json` — **new**
3. `profiles[active_profile].model` from `model_config.json` — existing generic fallback
4. `NEWSBRIEF_LLM_MODEL` env var / hardcoded default

Platform key is derived from `sys.platform` (`win32` → `windows`, `darwin` → `darwin`, else `linux`), overridable via `NEWSBRIEF_DEVICE_TYPE` env var for container deployments.

### 4. Re-run cadence

LLMfit analysis should be re-run when hardware changes meaningfully (new GPU, VRAM upgrade, new host added). Reports should be saved alongside prior reports on OneDrive Desktop for comparison.

---

## Consequences

### Positive

- The correct model for each host is selected automatically without any manual configuration after initial profile assignment
- `qwen2.5:32b` is retired from the quality slot where it was marginal — output quality improves on Windows
- `deepseek-r1:14b` as the Windows quality model brings chain-of-thought reasoning to complex multi-source stories
- The user-facing profile concept (fast / balanced / quality) is unchanged; device awareness is transparent
- Hardware analysis is now documented and reproducible

### Negative

- Two sets of model assignments to maintain; adding a third machine requires a new `device_profiles` entry and LLMfit analysis
- macOS model tags must be verified and pulled before the darwin block is live (Issue #318)
- `deepseek-r1:14b` has a higher time-to-first-token (~1.5 s) due to chain-of-thought generation; this is a latency tradeoff for the quality profile
- LLMfit estimates diverge from real Ollama CUDA performance (estimates run ~3× low on Windows); re-analysis after hardware changes should include live benchmark runs

---

## Related ADRs

- [ADR-0025: LLM Model Selection and Profile Strategy](0025-llm-model-selection.md)
- [ADR-0032: Cross-Platform Continuous Delivery Strategy](0032-cross-platform-cd-strategy.md)

## References

- GitHub milestone: [v0.9.4 — Model Optimisation & Platform Intelligence](https://github.com/Deim0s13/newsbrief/milestone/46)
- Issue #315 — Write ADR-0033
- Issue #316 — Add model specs to model_config.json
- Issue #317 — Add device_profiles block
- Issue #318 — Verify macOS models on MBP
- Issue #319 — Implement device-aware model resolution in SettingsService
- Issue #320 — Surface effective model in /config UI
- Issue #321 — Unit tests for device-aware model resolution
- Issue #322 — Update MODEL-PROFILES.md and ARCHITECTURE.md
