import { redirect } from "next/navigation";

export default function Home() {
  // The dashboard is open to everyone (residents joining via the shared link).
  // Login is optional and only the village chief needs it for /manage.
  redirect("/app");
}
