/* eslint-disable @next/next/no-img-element */
import { cx } from "@/lib/format";

/** Maps provider / connection / tool / format ids used by the API to files in /public/logos (see SOURCES.md). */
const LOGOS: Record<string, string> = {
  anthropic: "anthropic.svg",
  claude: "claude.svg",
  claude_code: "claudecode.svg",
  claudecode: "claudecode.svg",
  claude_desktop: "claude.svg",
  openai: "openai.png",
  openai_images: "openai.png",
  codex: "openai.png",
  gemini: "googlegemini.svg",
  google_gemini: "googlegemini.svg",
  gemini_cli: "googlegemini.svg",
  google: "google.svg",
  imagen: "google.svg",
  veo: "google.svg",
  openrouter: "openrouter.svg",
  litellm: "litellm.png",
  groq: "groq.png",
  deepseek: "deepseek.svg",
  mistral: "mistralai.svg",
  bedrock: "aws.png",
  aws: "aws.png",
  aws_bedrock: "aws.png",
  ollama: "ollama.svg",
  higgsfield: "higgsfield.png",
  runway: "runway.png",
  flux: "blackforestlabs.png",
  bfl: "blackforestlabs.png",
  fal: "fal.png",
  pexels: "pexels.svg",
  stock: "pexels.svg",
  cursor: "cursor.svg",
  mcp: "modelcontextprotocol.svg",
  google_slides: "googleslides.svg",
  gslides: "googleslides.svg",
  slides: "googleslides.svg",
  google_sheets: "googlesheets.svg",
  gsheets: "googlesheets.svg",
  sheets: "googlesheets.svg",
};

function norm(id: string): string {
  return id.trim().toLowerCase().replace(/[\s.-]+/g, "_");
}

export function logoFor(id: string): string | null {
  const file = LOGOS[norm(id)];
  return file ? `/logos/${file}` : null;
}

/** A brand mark in a neutral rounded tile. Falls back to an initial when no verified logo exists. */
export function ProviderLogo({ id, label, size = 22, className }: { id: string; label?: string; size?: number; className?: string }) {
  const src = logoFor(id);
  const name = label ?? id;
  return (
    <span
      className={cx("inline-flex shrink-0 items-center justify-center overflow-hidden rounded-[6px] border border-line bg-white", className)}
      style={{ width: size, height: size }}
      aria-hidden
    >
      {src ? (
        <img src={src} alt="" width={size} height={size} className={src.endsWith(".svg") ? "h-[70%] w-[70%] object-contain" : "h-full w-full object-cover"} />
      ) : (
        <span className="text-[11px] font-bold leading-none text-body">{name.replace(/[^A-Za-z0-9]/g, "").charAt(0).toUpperCase() || "?"}</span>
      )}
    </span>
  );
}
