import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/login.tsx"),
  route("search", "routes/search.tsx"),
] satisfies RouteConfig;
