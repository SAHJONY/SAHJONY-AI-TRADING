import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { VisualThemes, type ThemeKey } from "../lib/visualThemes";

const Canvas = dynamic(() => import("@react-three/fiber").then(mod => mod.Canvas), { ssr: false });

interface Props {
  theme?: ThemeKey;
}

export const UniversalCanvas: React.FC<Props> = ({ theme = "voiceAndAI" }) => {
  const [available, setAvailable] = useState(true);

  useEffect(() => {
    import("@react-three/fiber").catch(() => setAvailable(false));
  }, []);

  if (!available) {
    return <div className="flex items-center justify-center h-full w-full bg-black text-white">Graphics unavailable</div>;
  }

  const cfg = VisualThemes[theme];

  // Simple mapping – use geometry name directly if supported by three.js
  const geometry = (() => {
    switch (cfg.geometry) {
      case "torusKnot":
        return <torusKnotGeometry args={[1, 0.4, 100, 16]} />;
      case "particleBufferMesh":
        return <sphereGeometry args={[1, 32, 32]} />; // placeholder for particles
      case "icosahedron":
        return <icosahedronGeometry args={[1, 0]} />;
      default:
        return <sphereGeometry args={[1, 32, 32]} />;
    }
  })();

  return (
    <Canvas camera={{ position: [0, 0, 5] }}>
      <ambientLight intensity={0.5} />
      <directionalLight position={[5, 5, 5]} intensity={0.8} />
      <mesh rotation={[0, 0, 0]}>
        {geometry}
        <meshStandardMaterial
          color={cfg.color}
          roughness={cfg.roughness}
          wireframe={cfg.wireframe}
        />
      </mesh>
    </Canvas>
  );
};
