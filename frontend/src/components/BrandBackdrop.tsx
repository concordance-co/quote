export default function BrandBackdrop() {
  return (
    <>
      <div
        className="pointer-events-none fixed inset-0 opacity-16 mix-blend-multiply"
        style={{
          zIndex: -20,
          backgroundImage: "url('/brand/noise-tile.svg')",
          backgroundRepeat: "repeat",
          backgroundSize: "180px 180px",
        }}
        aria-hidden="true"
      />
      <div
        className="pointer-events-none fixed inset-0 opacity-35"
        style={{
          zIndex: -19,
          background:
            "linear-gradient(rgba(18,16,16,0) 50%, rgba(0,0,0,0.05) 50%), linear-gradient(90deg, rgba(255,0,0,0.02), rgba(255,0,0,0.01), rgba(255,0,0,0.02))",
          backgroundSize: "100% 3px, 3px 100%",
        }}
        aria-hidden="true"
      />
    </>
  );
}
