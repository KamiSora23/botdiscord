"use client";

import * as Popover from "@radix-ui/react-popover";
import { Braces, Smile } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useRef, useState } from "react";

import { inputClass } from "@/components/ui";
import { VAR_RE, VARIABLES } from "@/lib/messages";
import { cn } from "@/lib/utils";

const EMOJIS = "😀 😃 😄 😁 😆 😅 😂 🤣 😊 😇 🙂 😉 😍 🥰 😘 😎 🤩 🥳 😏 🤔 🤗 🙌 👏 👋 🤝 👍 👎 🙏 💪 ✌️ 👀 🎉 🎊 🎁 🎈 ✨ ⭐ 🌟 🔥 💯 ❤️ 🧡 💛 💚 💙 💜 🖤 🤍 💖 💬 📢 📣 🔔 📌 📎 ✅ ❌ ⚠️ ❗ ❓ ➡️ ⬅️ 🔗 🛡️ ⚙️ 🎮 🎵 🎨 💻 📚 🏆 🥇 🎫 💡 🚀 🌈 ☕ 🍕".split(" ");

function Highlighted({ text, known: knownList }: { text: string; known: readonly string[] }) {
  const out: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(VAR_RE)) {
    out.push(text.slice(last, m.index));
    const known = knownList.includes(m[1]!);
    out.push(
      <span key={m.index} className={known ? "rounded bg-primary/20 text-primary-text" : "text-danger underline decoration-wavy"}>
        {m[0]}
      </span>,
    );
    last = m.index! + m[0].length;
  }
  out.push(text.slice(last));
  return <>{out}{"\n"}</>;
}

/**
 * Campo de texto con variables resaltadas, autocompletado al escribir "{", botón de variables y emojis
 * (docs/NEXUS_UI_SPEC.md §5.2).
 */
export function VariableInput({ id, value, onChange, max, multiline = false, rows = 3, placeholder, invalid, describedBy, extraVariables = [] }: {
  id: string; value: string; onChange: (v: string) => void; max: number; multiline?: boolean; rows?: number;
  placeholder?: string; invalid?: boolean; describedBy?: string; extraVariables?: readonly string[];
}) {
  const allVars = [...extraVariables, ...VARIABLES];
  const t = useTranslations("editor");
  const ref = useRef<HTMLTextAreaElement>(null);
  const overlay = useRef<HTMLDivElement>(null);
  const listId = useId();
  const [suggest, setSuggest] = useState<{ query: string; start: number } | null>(null);
  const [active, setActive] = useState(0);

  const options = suggest ? allVars.filter((v) => v.startsWith(suggest.query)) : [];
  const count = value.length;

  const insertAt = (text: string, start: number, end: number) => {
    const next = value.slice(0, start) + text + value.slice(end);
    onChange(next);
    requestAnimationFrame(() => {
      const el = ref.current;
      if (el) {
        el.focus();
        el.setSelectionRange(start + text.length, start + text.length);
      }
    });
  };

  const insert = (text: string) => {
    const el = ref.current;
    const s = el?.selectionStart ?? value.length;
    const e = el?.selectionEnd ?? value.length;
    insertAt(text, s, e);
  };

  const onInput = (v: string) => {
    onChange(multiline ? v : v.replace(/\n/g, " "));
    const el = ref.current;
    const caret = el?.selectionStart ?? v.length;
    const m = /\{([a-z_.]*)$/.exec(v.slice(0, caret));
    setSuggest(m ? { query: m[1]!, start: caret - m[0].length } : null);
    setActive(0);
  };

  const choose = (name: string) => {
    if (!suggest) return;
    const caret = ref.current?.selectionStart ?? value.length;
    insertAt(`{${name}}`, suggest.start, caret);
    setSuggest(null);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (suggest && options.length) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((a) => (a + 1) % options.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((a) => (a - 1 + options.length) % options.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        choose(options[active]!);
        return;
      }
      if (e.key === "Escape") {
        setSuggest(null);
        return;
      }
    }
    if (!multiline && e.key === "Enter") e.preventDefault();
  };

  const syncScroll = () => {
    if (overlay.current && ref.current) overlay.current.scrollTop = ref.current.scrollTop;
  };

  const shared = "whitespace-pre-wrap break-words px-3 py-2 text-sm leading-6 font-sans";

  return (
    <div className="relative">
      <div className="relative">
        <div
          ref={overlay}
          aria-hidden
          className={cn(inputClass, shared, "pointer-events-none absolute inset-0 overflow-hidden pr-20 text-text")}
        >
          <Highlighted text={value} known={allVars} />
        </div>
        <textarea
          ref={ref}
          id={id}
          value={value}
          rows={multiline ? rows : 1}
          placeholder={placeholder}
          onChange={(e) => onInput(e.target.value)}
          onKeyDown={onKeyDown}
          onScroll={syncScroll}
          onBlur={() => setTimeout(() => setSuggest(null), 150)}
          aria-invalid={invalid || count > max}
          aria-describedby={describedBy}
          aria-autocomplete="list"
          aria-controls={suggest ? listId : undefined}
          spellCheck={false}
          className={cn(
            inputClass,
            shared,
            "relative resize-y bg-transparent pr-20 text-transparent caret-text selection:bg-primary/40 selection:text-text",
            !multiline && "resize-none overflow-hidden",
          )}
        />
        <div className="absolute right-1.5 top-1.5 flex gap-0.5">
          <EmojiButton onPick={insert} label={t("emoji")} />
          <VariableButton vars={allVars} onPick={(v) => insert(`{${v}}`)} label={t("variables")} />
        </div>
      </div>
      <div className="mt-1 flex justify-end">
        <span className={cn("text-[12px] tabular-nums", count > max ? "text-danger" : count > max * 0.9 ? "text-warning" : "text-muted")}>
          {count} / {max}
        </span>
      </div>
      {suggest && options.length > 0 && (
        <ul id={listId} role="listbox" className="absolute left-0 top-full z-30 mt-1 max-h-56 w-64 overflow-y-auto rounded-lg border border-border bg-sidebar p-1 shadow-xl">
          {options.map((o, i) => (
            <li
              key={o}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(o);
              }}
              className={cn("cursor-pointer rounded-md px-2 py-1.5", i === active && "bg-panel-hover")}
            >
              <code className="font-mono text-[13px] text-primary-text">{`{${o}}`}</code>
              <span className="ml-2 text-[12px] text-muted">{t(`vars.${o.replace(".", "_")}`)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function VariableButton({ onPick, label, vars }: { onPick: (v: string) => void; label: string; vars: readonly string[] }) {
  const t = useTranslations("editor");
  return (
    <Popover.Root>
      <Popover.Trigger className="grid size-7 place-items-center rounded-md text-muted hover:bg-panel-hover hover:text-text" aria-label={label}>
        <Braces className="size-4" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={6} className="z-50 w-80 rounded-xl border border-border bg-sidebar p-2 shadow-xl">
          <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</p>
          <ul className="max-h-72 overflow-y-auto">
            {vars.map((v) => (
              <li key={v}>
                <Popover.Close asChild>
                  <button type="button" onClick={() => onPick(v)} className="flex w-full items-baseline gap-2 rounded-md px-2 py-1.5 text-left hover:bg-panel-hover">
                    <code className="shrink-0 font-mono text-[13px] text-primary-text">{`{${v}}`}</code>
                    <span className="truncate text-[12px] text-muted">{t(`vars.${v.replace(".", "_")}`)}</span>
                  </button>
                </Popover.Close>
              </li>
            ))}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

function EmojiButton({ onPick, label }: { onPick: (v: string) => void; label: string }) {
  return (
    <Popover.Root>
      <Popover.Trigger className="grid size-7 place-items-center rounded-md text-muted hover:bg-panel-hover hover:text-text" aria-label={label}>
        <Smile className="size-4" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={6} className="z-50 grid w-72 grid-cols-8 gap-0.5 rounded-xl border border-border bg-sidebar p-2 shadow-xl">
          {EMOJIS.map((e) => (
            <Popover.Close asChild key={e}>
              <button type="button" onClick={() => onPick(e)} className="grid size-8 place-items-center rounded-md text-lg hover:bg-panel-hover" aria-label={e}>
                {e}
              </button>
            </Popover.Close>
          ))}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
