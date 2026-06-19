import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { NAV_ITEMS } from "./nav";
import { IconSearch, IconArrowRight } from "./icons";

/**
 * Cmd/Ctrl+K command palette for quick navigation.
 * - Focus is trapped within the panel while open.
 * - Arrow keys move the active item, Enter selects, Esc closes.
 * - Restores focus to the previously focused element on close.
 */
export default function CommandPalette({ open, onClose }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const panelRef = useRef(null);
  const lastFocused = useRef(null);

  const commands = NAV_ITEMS.map((item) => ({
    id: item.to,
    label: `Go to ${item.label}`,
    hint: "Navigate",
    Icon: item.Icon,
    run: () => navigate(item.to),
  }));

  const filtered = commands.filter((c) =>
    c.label.toLowerCase().includes(query.trim().toLowerCase())
  );

  // Reset transient state and manage focus when opening.
  useEffect(() => {
    if (open) {
      lastFocused.current = document.activeElement;
      setQuery("");
      setActive(0);
      // focus after paint
      requestAnimationFrame(() => inputRef.current?.focus());
    } else if (lastFocused.current instanceof HTMLElement) {
      lastFocused.current.focus();
    }
  }, [open]);

  // Keep active index in range as the list filters down.
  useEffect(() => {
    setActive((a) => Math.min(a, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  const select = useCallback(
    (cmd) => {
      if (!cmd) return;
      onClose();
      cmd.run();
    },
    [onClose]
  );

  const onKeyDown = (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (filtered.length ? (a + 1) % filtered.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) =>
        filtered.length ? (a - 1 + filtered.length) % filtered.length : 0
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      select(filtered[active]);
    } else if (e.key === "Tab") {
      // Trap focus — only the input is tabbable, so keep it here.
      e.preventDefault();
      inputRef.current?.focus();
    }
  };

  if (!open) return null;

  return (
    <div
      className="cmdk-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="cmdk-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        ref={panelRef}
        onKeyDown={onKeyDown}
      >
        <div className="cmdk-input-row">
          <IconSearch size={18} />
          <input
            ref={inputRef}
            className="cmdk-input"
            type="text"
            value={query}
            placeholder="Search pages…"
            aria-label="Search commands"
            aria-controls="cmdk-listbox"
            aria-activedescendant={
              filtered[active] ? `cmdk-opt-${active}` : undefined
            }
            role="combobox"
            aria-expanded="true"
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
          />
          <span className="kbd">Esc</span>
        </div>

        {filtered.length === 0 ? (
          <div className="cmdk-empty">No matching commands</div>
        ) : (
          <ul className="cmdk-list" role="listbox" id="cmdk-listbox">
            {filtered.map((cmd, i) => {
              const Icon = cmd.Icon;
              return (
                <li
                  key={cmd.id}
                  id={`cmdk-opt-${i}`}
                  role="option"
                  aria-selected={i === active}
                  className={`cmdk-item ${i === active ? "active" : ""}`}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    select(cmd);
                  }}
                >
                  <span className="ci-icon">
                    <Icon size={17} />
                  </span>
                  {cmd.label}
                  <span className="ci-hint">
                    <IconArrowRight size={13} />
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
