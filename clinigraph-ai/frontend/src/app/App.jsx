import { HeroSection } from '../features/platform/components/HeroSection';
import { BillingDashboard } from '../features/billing/components/BillingDashboard';
import { OperationsPanel } from '../features/platform/components/OperationsPanel';
import { PlatformAreasGrid } from '../features/platform/components/PlatformAreasGrid';
import { usePlatformSnapshot } from '../features/platform/hooks/usePlatformSnapshot';

export default function App() {
  const platformSnapshot = usePlatformSnapshot();

  return (
    <main className="page-shell">
      <HeroSection health={platformSnapshot.health} />
      <PlatformAreasGrid />
      <BillingDashboard />
      <OperationsPanel health={platformSnapshot.health} />
    </main>
  );
}