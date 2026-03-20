import { useUserAccessAdmin } from '../hooks/useUserAccessAdmin';
import { useI18n } from '../../../shared/i18n/I18nProvider';

const roleOptions = ['owner', 'admin', 'billing', 'clinician', 'auditor'];

export function UserAccessAdmin() {
  const { t } = useI18n();

  const {
    authToken,
    setAuthToken,
    tenantId,
    setTenantId,
    createInput,
    setCreateInput,
    members,
    loading,
    error,
    success,
    loadMembers,
    createMember,
    updateMember,
  } = useUserAccessAdmin();

  return (
    <section className="billing-panel">
      <div className="billing-panel__header">
        <p className="eyebrow">{t('access.eyebrow')}</p>
        <h2>{t('access.title')}</h2>
      </div>

      <div className="access-grid">
        <article className="billing-card">
          <h3>{t('access.authContext')}</h3>
          <label>
            {t('access.jwtToken')}
            <input
              type="password"
              placeholder={t('access.pasteBearer')}
              value={authToken}
              onChange={(event) => setAuthToken(event.target.value)}
            />
          </label>

          <label>
            {t('access.tenantId')}
            <input
              type="text"
              placeholder={t('access.tenantUuid')}
              value={tenantId}
              onChange={(event) => setTenantId(event.target.value)}
            />
          </label>

          <button type="button" onClick={loadMembers} disabled={loading}>
            {loading ? t('ui.loading') : t('access.loadMembers')}
          </button>
        </article>

        <article className="billing-card">
          <h3>{t('access.addOrAttach')}</h3>

          <label>
            {t('access.username')}
            <input
              type="text"
              value={createInput.username}
              onChange={(event) => setCreateInput((current) => ({ ...current, username: event.target.value }))}
              placeholder={t('access.usernameRequired')}
            />
          </label>

          <label>
            {t('access.email')}
            <input
              type="email"
              value={createInput.email}
              onChange={(event) => setCreateInput((current) => ({ ...current, email: event.target.value }))}
              placeholder={t('access.emailOptional')}
            />
          </label>

          <label>
            {t('access.password')}
            <input
              type="password"
              value={createInput.password}
              onChange={(event) => setCreateInput((current) => ({ ...current, password: event.target.value }))}
              placeholder={t('access.passwordOptional')}
            />
          </label>

          <label>
            {t('access.role')}
            <select
              value={createInput.role}
              onChange={(event) => setCreateInput((current) => ({ ...current, role: event.target.value }))}
            >
              {roleOptions.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>

          <button type="button" onClick={createMember} disabled={loading}>
            {t('access.createOrUpdate')}
          </button>
          {success ? <p className="billing-note">{success}</p> : null}
          {error ? <p className="billing-error">{error}</p> : null}
        </article>
      </div>

      <article className="billing-card access-members-table">
        <h3>{t('access.currentMemberships')}</h3>
        <div className="access-table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('access.user')}</th>
                <th>{t('access.email')}</th>
                <th>{t('access.role')}</th>
                <th>{t('access.status')}</th>
                <th>{t('access.action')}</th>
              </tr>
            </thead>
            <tbody>
              {members.map((member) => (
                <tr key={member.membership_id}>
                  <td>{member.username}</td>
                  <td>{member.email || t('ui.na')}</td>
                  <td>{member.role}</td>
                  <td>{member.is_active ? t('access.active') : t('access.inactive')}</td>
                  <td className="access-actions">
                    <select
                      defaultValue={member.role}
                      onChange={(event) => updateMember(member.membership_id, { role: event.target.value })}
                      disabled={loading}
                    >
                      {roleOptions.map((role) => (
                        <option key={`${member.membership_id}-${role}`} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="billing-secondary-button"
                      onClick={() => updateMember(member.membership_id, { is_active: !member.is_active })}
                      disabled={loading}
                    >
                      {member.is_active ? t('access.deactivate') : t('access.activate')}
                    </button>
                  </td>
                </tr>
              ))}
              {members.length === 0 ? (
                <tr>
                  <td colSpan="5">{t('access.noMemberships')}</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
