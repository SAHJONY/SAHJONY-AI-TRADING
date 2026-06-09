/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow builds to succeed even if TypeScript type errors are present
  typescript: {
    ignoreBuildErrors: true,
  },
  // Suppress noisy warnings for multiple lockfiles
  outputFileTracingRoot: './',
};
module.exports = nextConfig;
