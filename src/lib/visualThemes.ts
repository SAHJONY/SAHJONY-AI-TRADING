export const VisualThemes = {
  voiceAndAI: {
    geometry: "torusKnot",
    color: "#00E5A3",
    roughness: 0.1,
    wireframe: false,
    speed: 1.5
  },
  saasAndData: {
    geometry: "particleBufferMesh",
    color: "#00D4FF",
    roughness: 0.5,
    wireframe: true,
    speed: 0.8
  },
  eCommerceAndPremium: {
    geometry: "icosahedron",
    color: "#FFDF00",
    roughness: 0.0,
    wireframe: false,
    speed: 0.5
  }
} as const;

export type ThemeKey = keyof typeof VisualThemes;
