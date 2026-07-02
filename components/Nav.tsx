import Link from "next/link";

const Logo = (
  <svg viewBox="0 0 24 24">
    <path d="M12 3 3.8 8.2 12 13.4l8.2-5.2L12 3Z" />
    <path d="m3.8 12.2 8.2 5.2 8.2-5.2" />
    <path d="m3.8 16.2 8.2 5.2 8.2-5.2" />
  </svg>
);

export default function Nav({
  brandTitle, brandSub, brandHref, children,
}: {
  brandTitle: string;
  brandSub: string;
  brandHref: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <div className="scroll-progress" id="scroll-progress" />
      <nav className="nav-fixed" id="nav" aria-label="Navigazione principale">
        <div className="container">
          <div className="nav">
            <Link className="brand" href={brandHref}>
              <span className="brand-mark">{Logo}</span>
              <span><b>{brandTitle}</b><span>{brandSub}</span></span>
            </Link>
            <div className="nav-actions">{children}</div>
          </div>
        </div>
      </nav>
    </>
  );
}
