import { motion } from "framer-motion";
import { useAtomValue, useSetAtom } from "jotai";
import { useCallback, useState } from "react";
import { commandErrorAtom, wsConnectedAtom } from "../atoms";

type Props = {
  onSend: (text: string) => void;
};

export function CommandBar({ onSend }: Props) {
  const [value, setValue] = useState("");
  const connected = useAtomValue(wsConnectedAtom);
  const setCommandError = useSetAtom(commandErrorAtom);

  const submit = useCallback(() => {
    const t = value.trim();
    if (!t || !connected) return;
    setCommandError(null);
    onSend(t);
    setValue("");
  }, [value, connected, onSend, setCommandError]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-4 w-full max-w-md px-6"
    >
      <label className="sr-only" htmlFor="friday-command">
        Command for FRIDAY
      </label>
      <input
        id="friday-command"
        type="text"
        autoComplete="off"
        spellCheck={false}
        disabled={!connected}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            submit();
          }
        }}
        placeholder={connected ? "Type a command, press Enter" : "Connecting…"}
        className="w-full rounded-full border border-white/25 bg-white/[0.06] px-5 py-2.5 text-center text-sm text-white/95 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] outline-none backdrop-blur-md placeholder:text-white/35 focus:border-white/45 focus:ring-1 focus:ring-white/20 disabled:opacity-50"
      />
    </motion.div>
  );
}
