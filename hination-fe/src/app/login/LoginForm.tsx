"use client";

import { useActionState, useState } from "react";
import { EyeClosedIcon, EyeIcon } from "@phosphor-icons/react";

import { login, type LoginState } from "./actions";

const initialState: LoginState = {};

export function LoginForm() {
  const [state, formAction, isPending] = useActionState(login, initialState);
  const [showPassword, setShowPassword] = useState(false);

  return (
    <form
      action={formAction}
      className="mx-auto flex min-h-[260px] w-full max-w-[500px] justify-center px-9 pt-[20px] pb-[38px]"
      noValidate
    >
      <div className="w-full">
      <div className="grid gap-3.5">
        <label className="sr-only" htmlFor="username">
          Username
        </label>
        <input
          autoComplete="username"
          className="h-[42px] w-full rounded-[9px] border border-[#afafaf] bg-white px-[13px] text-xs text-[#333] shadow-[inset_0_1px_1px_rgb(0_0_0_/_3%)] outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-[#777] focus:border-[#5d5d5d] focus:shadow-[0_0_0_3px_rgb(61_61_61_/_12%)]"
          id="username"
          name="username"
          placeholder="Username"
          required
          type="text"
        />

        <label className="sr-only" htmlFor="password">
          Password
        </label>
        <div className="relative">
          <input
            autoComplete="current-password"
            className="h-[42px] w-full rounded-[9px] border border-[#afafaf] bg-white py-0 pr-[45px] pl-[13px] text-xs text-[#333] shadow-[inset_0_1px_1px_rgb(0_0_0_/_3%)] outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-[#777] focus:border-[#5d5d5d] focus:shadow-[0_0_0_3px_rgb(61_61_61_/_12%)]"
            id="password"
            name="password"
            placeholder="Password"
            required
            type={showPassword ? "text" : "password"}
          />
          <button
            aria-label={showPassword ? "Hide password" : "Show password"}
            className="absolute top-1/2 right-2.5 grid size-7 -translate-y-1/2 cursor-pointer place-items-center rounded-[5px] border-0 bg-transparent p-0 text-[#777] hover:bg-[#efefef] hover:text-[#343434] focus-visible:bg-[#efefef] focus-visible:text-[#343434] focus-visible:outline-none"
            onClick={() => setShowPassword((currentValue) => !currentValue)}
            type="button"
          >
            {showPassword ? <EyeClosedIcon aria-hidden size={18} /> : <EyeIcon aria-hidden size={18} />}
          </button>
        </div>
      </div>

      <p aria-live="polite" className="mt-2 min-h-[34px] text-[11px] leading-[1.35] text-[#a33d3d]" role="status">
        {state.error}
      </p>

      <button
        className="mx-auto block h-[28px] w-full cursor-pointer rounded-[18px] border-0 bg-[#777] text-[11px] font-semibold text-white shadow-[0_1px_1px_rgb(0_0_0_/_14%)] transition-[background-color,transform,opacity] duration-150 hover:not-disabled:-translate-y-px hover:not-disabled:bg-[#565656] focus-visible:outline-3 focus-visible:outline-[#3d3d3d]/25 focus-visible:outline-offset-3 disabled:cursor-wait disabled:opacity-70"
        disabled={isPending}
        type="submit"
      >
        {isPending ? "Logging in..." : "Log in"}
      </button>
      </div>
    </form>
  );
}
