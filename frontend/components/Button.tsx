"use client";

import { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
};

export function Button({
  variant = "primary",
  className = "",
  children,
  ...rest
}: ButtonProps) {
  const base =
    "inline-flex items-center justify-center min-h-[48px] rounded-xl px-5 text-base font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60";
  const palette =
    variant === "primary"
      ? "bg-brand text-white hover:bg-brand-dark active:bg-brand-dark"
      : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-100";
  return (
    <button {...rest} className={`${base} ${palette} ${className}`}>
      {children}
    </button>
  );
}
