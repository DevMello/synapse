import { createBrowserRouter } from "react-router-dom";
import { AppLayout } from "./components/Shell";
import Tweaks from "./screens/Tweaks";

import Dashboard from "./screens/Dashboard";
import Agents from "./screens/Agents";
import Daemons from "./screens/Daemons";
import Connect from "./screens/Connect";
import Runs from "./screens/Runs";
import Approvals from "./screens/Approvals";
import Alerts from "./screens/Alerts";
import Marketplace from "./screens/Marketplace";
import Webhooks from "./screens/Webhooks";
import Notifications from "./screens/Notifications";
import Settings from "./screens/Settings";
import AgentDetail from "./screens/agent/AgentDetail";

export const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <AppLayout tweaks={<Tweaks />} />,
      children: [
        { index: true, element: <Dashboard /> },
        { path: "agents", element: <Agents /> },
        { path: "agents/:agentId", element: <AgentDetail /> },
        { path: "daemons", element: <Daemons /> },
        { path: "connect", element: <Connect /> },
        { path: "runs", element: <Runs /> },
        { path: "approvals", element: <Approvals /> },
        { path: "alerts", element: <Alerts /> },
        { path: "marketplace", element: <Marketplace /> },
        { path: "webhooks", element: <Webhooks /> },
        { path: "notifications", element: <Notifications /> },
        { path: "settings", element: <Settings /> },
      ],
    },
  ],
  { future: { v7_relativeSplatPath: true } },
);
