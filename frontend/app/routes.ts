import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/search.tsx"),
  route("jobs/:companyId", "routes/jobs.tsx"),
] satisfies RouteConfig;
