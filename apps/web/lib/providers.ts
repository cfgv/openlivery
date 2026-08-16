// Supported AI providers (must match backend app/services/providers.py).
export const PROVIDERS = [
  {
    id: "openai",
    label: "OpenAI",
    keyPlaceholder: "sk-proj-...",
    keyUrl: "https://platform.openai.com/api-keys",
    models: [
      "gpt-5.6-sol",
      "gpt-5.6-terra",
      "gpt-5.6-luna",
      "gpt-5.5",
      "gpt-5.4",
      "gpt-5.4-mini",
      "gpt-5.4-nano",
      "gpt-5.2",
      "gpt-5.1",
      "gpt-5",
      "gpt-5-mini",
      "gpt-5-nano",
      "gpt-4.1",
      "gpt-4.1-mini",
      "gpt-4.1-nano",
    ],
  },
  {
    id: "anthropic",
    label: "Anthropic",
    keyPlaceholder: "sk-ant-...",
    keyUrl: "https://console.anthropic.com/settings/keys",
    models: [
      "claude-opus-4-8",
      "claude-opus-4-7",
      "claude-opus-4-6",
      "claude-sonnet-4-6",
      "claude-sonnet-4-5",
      "claude-haiku-4-5",
    ],
  },
] as const;

export type ProviderId = (typeof PROVIDERS)[number]["id"];

// Transcription models for the audio-recognition capability (OpenAI).
export const AUDIO_MODELS = ["gpt-transcribe", "whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe", "gpt-4o-transcribe-diarize"] as const;
// Vision-capable models for the image-recognition capability.
export const IMAGE_MODELS = ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-4.1", "gpt-4.1-mini", "gpt-5.5", "gpt-5.4", "gpt-5", "gpt-5-mini"] as const;

export function providerLabel(id: string): string {
  return PROVIDERS.find((p) => p.id === id)?.label ?? id;
}

export function modelsFor(id: string): readonly string[] {
  return PROVIDERS.find((p) => p.id === id)?.models ?? [];
}

// ~4 characters per token: same approximation as the backend, for the token
// counter in the agent creation wizard.
export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

// Approximate context window (in tokens) per model family, used only for the
// "context window usage" bar. Values are representative, not exact.
export function modelContextWindow(id: string): number {
  if (id.startsWith("gpt-4.1")) return 1_000_000;
  if (id.startsWith("gpt-5")) return 400_000;
  if (id.startsWith("claude")) return 200_000;
  return 128_000;
}
