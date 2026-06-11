/** @type {import('next').NextConfig} */
const nextConfig = {
  // Pin the workspace root so Next doesn't infer it from stray parent lockfiles.
  outputFileTracingRoot: import.meta.dirname,
}
export default nextConfig
