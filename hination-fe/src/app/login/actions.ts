"use server";

import { redirect } from "next/navigation";

import { authenticate, createSession } from "@/lib/auth";

export type LoginState = {
  error?: string;
};

export async function login(_: LoginState, formData: FormData): Promise<LoginState> {
  const username = String(formData.get("username") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (!username || !password) {
    return { error: "Enter your username and password." };
  }

  const user = authenticate(username, password);

  if (!user) {
    return { error: "The username or password is incorrect." };
  }

  await createSession(user.id);
  redirect("/app");
}
