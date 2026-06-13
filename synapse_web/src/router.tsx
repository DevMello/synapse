import { lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppLayout } from "./components/Shell";
import Tweaks from "./screens/Tweaks";

// Screens are code-split: each becomes its own async chunk fetched on navigation,
// so the initial load is just the shell + the landing route. The Suspense boundary
// lives in AppLayout (components/Shell.tsx), which wraps the routed <Outlet />.
const Dashboard = lazy(() => import("./screens/Dashboard"));
const Agents = lazy(() => import("./screens/Agents"));
const Daemons = lazy(() => import("./screens/Daemons"));
const Connect = lazy(() => import("./screens/Connect"));
const Runs = lazy(() => import("./screens/Runs"));
const Approvals = lazy(() => import("./screens/Approvals"));
const Alerts = lazy(() => import("./screens/Alerts"));
const Marketplace = lazy(() => import("./screens/Marketplace"));
const Webhooks = lazy(() => import("./screens/Webhooks"));
const Notifications = lazy(() => import("./screens/Notifications"));
const Settings = lazy(() => import("./screens/Settings"));
const AgentDetail = lazy(() => import("./screens/agent/AgentDetail"));
const Flows = lazy(() => import("./screens/Flows"));
const FlowCanvas = lazy(() => import("./screens/flow/FlowCanvas"));
const Comparisons = lazy(() => import("./screens/Comparisons"));
const ComparisonView = lazy(() => import("./screens/comparison/ComparisonView"));
const Organizations = lazy(() => import("./screens/Organizations"));
const OrgSettings = lazy(() => import("./screens/OrgSettings"));

export const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <AppLayout tweaks={<Tweaks />} />,
      children: [
        { index: true, element: <Dashboard /> },
        { path: "agents", element: <Agents /> },
        { path: "agents/:agentId", element: <AgentDetail /> },
        { path: "flows", element: <Flows /> },
        { path: "flows/:flowId", element: <FlowCanvas /> },
        { path: "comparisons", element: <Comparisons /> },
        { path: "comparisons/:groupId", element: <ComparisonView /> },
        { path: "daemons", element: <Daemons /> },
        { path: "connect", element: <Connect /> },
        { path: "runs", element: <Runs /> },
        { path: "approvals", element: <Approvals /> },
        { path: "alerts", element: <Alerts /> },
        { path: "marketplace", element: <Marketplace /> },
        { path: "webhooks", element: <Webhooks /> },
        { path: "notifications", element: <Notifications /> },
        { path: "settings", element: <Settings /> },
        { path: "organizations", element: <Organizations /> },
        { path: "org/:orgId/settings", element: <OrgSettings /> },
        { path: "account/security", element: <Navigate to="/settings" replace /> },
      ],
    },
  ],
  { future: { v7_relativeSplatPath: true } },
);
