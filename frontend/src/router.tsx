import { Suspense, lazy, type ComponentType } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";

const Agent = lazy(() => import("@/pages/Agent").then((m) => ({ default: m.Agent })));
const Settings = lazy(() =>
  import("@/pages/Settings").then((m) => ({ default: m.Settings })),
);
const Monitor = lazy(() =>
  import("@/pages/Monitor").then((m) => ({ default: m.Monitor })),
);

function PageLoader() {
  return (
    <div className="flex h-[60vh] items-center justify-center text-muted-foreground">
      Loading…
    </div>
  );
}

function wrap(Component: ComponentType) {
  return (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Navigate to="/agent" replace /> },
      { path: "/agent", element: wrap(Agent) },
      { path: "/monitor", element: wrap(Monitor) },
      { path: "/settings", element: wrap(Settings) },
    ],
  },
]);
