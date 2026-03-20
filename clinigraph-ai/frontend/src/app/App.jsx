import { HeroSection } from '../features/platform/components/HeroSection';
import { UserAccessAdmin } from '../features/access/components/UserAccessAdmin';
import { BillingDashboard } from '../features/billing/components/BillingDashboard';
import { OperationsPanel } from '../features/platform/components/OperationsPanel';
import { PlatformAreasGrid } from '../features/platform/components/PlatformAreasGrid';
import { usePlatformSnapshot } from '../features/platform/hooks/usePlatformSnapshot';
import { LanguageSwitcher } from '../shared/ui/LanguageSwitcher';
import { AgentQueryPanel } from '../features/platform/components/AgentQueryPanel';
import { OncologyQueryPanel } from '../features/platform/components/OncologyQueryPanel';
import { MedicalQueryPanel } from '../features/platform/components/MedicalQueryPanel';
import { PatientCaseAnalyzePanel } from '../features/platform/components/PatientCaseAnalyzePanel';
import { useI18n } from '../shared/i18n/I18nProvider';

export default function App() {
  const platformSnapshot = usePlatformSnapshot();
  const { t } = useI18n();

  return (
    <main className="page-shell">
      <div className="page-toolbar">
        <LanguageSwitcher />
      </div>
      <HeroSection health={platformSnapshot.health} />
      <PlatformAreasGrid />
      <BillingDashboard />
      <UserAccessAdmin />
      <section className="billing-panel">
        <div className="billing-panel__header">
          <p className="eyebrow">{t('genai.title')}</p>
          <h2>{t('genai.subtitle')}</h2>
        </div>
        <div className="billing-grid">
          <AgentQueryPanel />
          <OncologyQueryPanel />
        </div>
        <div className="billing-grid">
          <MedicalQueryPanel />
          <PatientCaseAnalyzePanel />
        </div>
      </section>
      <OperationsPanel health={platformSnapshot.health} />
    </main>
  );
}