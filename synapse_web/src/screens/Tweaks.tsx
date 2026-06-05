import { Modal, ScreenStub } from "../components/Common";
import { useUI } from "../store/ui";

// Tweaks panel — STUB: a worker fills this in (plan unit 22). Three expressive
// controls (Density / Accent mood / Liveness) that reshape the console's feel.
// Mounted once in the app layout; opened from the header's sliders control.
export default function Tweaks() {
  const open = useUI((s) => s.tweaksOpen);
  const setTweaks = useUI((s) => s.setTweaks);
  return (
    <Modal open={open} onClose={() => setTweaks(false)} width={520}>
      <div style={{ padding: 24 }}>
        <ScreenStub name="Tweaks" note="Density · Accent mood · Liveness" />
      </div>
    </Modal>
  );
}
