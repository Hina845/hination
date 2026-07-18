import Image from "next/image";
import { redirect } from "next/navigation";

import { getSessionUser } from "@/lib/auth";

import { LoginBrand } from "./LoginBrand";
import { LoginForm } from "./LoginForm";

export default async function LoginPage() {
  const user = await getSessionUser();

  if (user) {
    redirect("/app");
  }

  return (
    <main className="grid min-h-svh overflow-hidden bg-white min-[801px]:grid-cols-[minmax(360px,39%)_1fr]">
      <section
        aria-label="Sign in"
        className="grid min-h-svh place-items-center px-5 py-8 min-[801px]:min-h-full min-[801px]:px-[18px] min-[801px]:py-[42px]"
      >
        <div className="w-full flex flex-col justify-center">
          <LoginBrand />
          <LoginForm />
        </div>
      </section>

      <section aria-label="Dien Bien Phu" className="relative hidden min-h-svh bg-[#26412d] min-[801px]:block">
        <Image
          alt="Aerial view of the Dien Bien Phu Victory Museum"
          className="object-cover object-center"
          fill
          priority
          sizes="(max-width: 800px) 0px, 61vw"
          src="/78f5cf01b85f8940679f4113c8b7c06f9bd75d28.png"
        />
      </section>
    </main>
  );
}
