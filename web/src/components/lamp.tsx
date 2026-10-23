"use client";
import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Color, ShaderMaterial, type Mesh } from "three";
import { RoundedBox } from "@react-three/drei";

const vertex = /* glsl */ `
  varying float vY; varying vec3 vN; varying vec3 vV;
  void main() {
    vY = position.y; vN = normalize(normalMatrix * normal);
    vec4 mv = modelViewMatrix * vec4(position, 1.0); vV = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }`;

// A luz nasce na base e some para o topo; o grão deixa a superfície com cara de tecido, como na referência.
const fragment = /* glsl */ `
  uniform vec3 uColor; uniform float uPulse; varying float vY; varying vec3 vN; varying vec3 vV;
  float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
  void main() {
    float t = clamp((0.55 - vY) / 1.55, 0.0, 1.0);
    float glow = pow(t, 1.7) * uPulse;
    float fres = pow(1.0 - max(dot(normalize(vN), normalize(vV)), 0.0), 2.5);
    vec3 base = vec3(0.075, 0.065, 0.055);
    vec3 col = mix(base, uColor, glow) + uColor * fres * 0.18 * (0.4 + glow);
    col += (hash(gl_FragCoord.xy) - 0.5) * 0.035;
    gl_FragColor = vec4(col, 1.0);
  }`;

function Body({ color, level }: { color: string; level: number }) {
  const mesh = useRef<Mesh>(null);
  const target = useMemo(() => new Color(color), [color]);
  const mat = useMemo(() => new ShaderMaterial({ vertexShader: vertex, fragmentShader: fragment, uniforms: { uColor: { value: new Color(color) }, uPulse: { value: 1 } } }), []); // eslint-disable-line react-hooks/exhaustive-deps
  useFrame(({ clock }, dt) => {
    const t = clock.elapsedTime * (0.8 + level * 1.4); // a cobrança acelera o pulso
    (mat.uniforms.uColor.value as Color).lerp(target, Math.min(1, dt * 3));
    mat.uniforms.uPulse.value = 1 + Math.sin(t) * 0.07;
    if (mesh.current) mesh.current.scale.setScalar(1 + Math.sin(t) * 0.008);
  });
  return <RoundedBox ref={mesh} args={[1.5, 2, 0.7]} radius={0.62} smoothness={10} material={mat} />;
}

export function Lamp({ color, level, label }: { color: string; level: number; label: string }) {
  return (
    <div className="aspect-[3/4] w-full max-w-[300px]" role="img" aria-label={label}>
      <Canvas camera={{ position: [0, 0, 4.4], fov: 36 }} dpr={[1, 2]} gl={{ alpha: true }}>
        <Body color={color} level={level} />
      </Canvas>
    </div>
  );
}
