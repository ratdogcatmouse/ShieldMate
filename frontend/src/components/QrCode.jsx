import { QRCodeSVG } from "qrcode.react";

export default function QrCode({ value, size = 150 }) {
  return (
    <div style={{ background: "#fff", padding: 10, borderRadius: 12, border: "1px solid var(--line)", alignSelf: "flex-start" }}>
      <QRCodeSVG value={value} size={size} />
    </div>
  );
}
