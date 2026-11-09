import { useCallback, useEffect, useState } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { createEmergencyContact, deleteEmergencyContact, getEmergencyContacts, updateEmergencyContact } from '../../utils/sync';
import type { EmergencyContact } from '../../utils/sync';

const empty = { contactName: '', relationship: '', phoneNumber: '', isPrimary: false };
const field = 'mt-1 w-full rounded-md border border-clinical-border px-3 py-2 text-sm';

export function EmergencyContacts({ legacyValue }: { legacyValue?: string }) {
  const [contacts, setContacts] = useState<EmergencyContact[]>([]);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    setLoading(true);
    try { setContacts((await getEmergencyContacts()).contacts); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load emergency contacts.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    void refresh();
    const reconnect = () => void refresh();
    window.addEventListener('online', reconnect);
    window.addEventListener('focus', reconnect);
    return () => { window.removeEventListener('online', reconnect); window.removeEventListener('focus', reconnect); };
  }, [refresh]);
  const save = async () => {
    if (saving) return;
    if (!form.contactName.trim() || !form.relationship.trim() || !/^\+[1-9][0-9]{5,14}$/.test(form.phoneNumber)) {
      setError('Enter a name, relationship, and phone number with country code, such as +201001234567.'); return;
    }
    setSaving(true); setError('');
    try {
      const payload = { ...form, contactName: form.contactName.trim(), relationship: form.relationship.trim() };
      if (editing) await updateEmergencyContact(editing, payload); else await createEmergencyContact(payload);
      await refresh(); setForm(empty); setEditing(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save the contact.'); }
    finally { setSaving(false); }
  };
  const remove = async (contact: EmergencyContact) => {
    if (saving || !window.confirm(`Delete ${contact.contactName} from your emergency contacts?`)) return;
    setSaving(true); setError('');
    try { await deleteEmergencyContact(contact.id); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not delete the contact.'); }
    finally { setSaving(false); }
  };
  const makePrimary = async (contact: EmergencyContact) => {
    if (saving || contact.isPrimary) return;
    setSaving(true); setError('');
    try { await updateEmergencyContact(contact.id, { isPrimary: true }); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not change the primary contact.'); }
    finally { setSaving(false); }
  };
  return <section className="border-t border-clinical-border pt-5">
    <h3 className="font-semibold">Emergency contacts</h3>
    <p className="mt-1 text-sm text-clinical-muted">These contacts are stored for reference. Adding one does not call or alert anyone.</p>
    {legacyValue ? <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm"><strong>Legacy information</strong><p className="mt-1 break-words">{legacyValue}</p><p className="mt-1 text-xs">Review this text and explicitly add a structured contact below. It will not be parsed or deleted automatically.</p></div> : null}
    {loading ? <p className="mt-3 text-sm text-clinical-muted">Loading contacts…</p> : contacts.length ? <ul className="mt-3 space-y-2">{contacts.map((contact) => <li key={contact.id} className="rounded-md border border-clinical-border p-3 text-sm"><div className="flex justify-between gap-3"><div><strong>{contact.contactName}</strong>{contact.isPrimary ? <span className="ml-2 rounded bg-clinical-secondary px-2 py-0.5 text-xs">Primary</span> : null}<p>{contact.relationship} · {contact.phoneNumber}</p></div><div className="flex gap-2"><button type="button" disabled={saving} onClick={() => { setEditing(contact.id); setForm({ contactName: contact.contactName, relationship: contact.relationship, phoneNumber: contact.phoneNumber, isPrimary: contact.isPrimary }); }} aria-label={`Edit ${contact.contactName}`}><Pencil size={17} /></button><button type="button" disabled={saving} onClick={() => void remove(contact)} aria-label={`Delete ${contact.contactName}`} className="text-clinical-critical"><Trash2 size={17} /></button></div></div>{!contact.isPrimary ? <button type="button" disabled={saving} onClick={() => void makePrimary(contact)} className="mt-2 text-xs font-semibold text-clinical-primary">Make primary</button> : null}</li>)}</ul> : <p className="mt-3 text-sm text-clinical-muted">No structured emergency contacts yet.</p>}
    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      <label className="text-sm font-semibold">Name<input value={form.contactName} onChange={(event) => setForm({ ...form, contactName: event.target.value })} className={field} /></label>
      <label className="text-sm font-semibold">Relationship<input value={form.relationship} onChange={(event) => setForm({ ...form, relationship: event.target.value })} className={field} /></label>
      <label className="text-sm font-semibold sm:col-span-2">Phone with country code<input type="tel" value={form.phoneNumber} onChange={(event) => setForm({ ...form, phoneNumber: event.target.value })} placeholder="+201001234567" className={field} /></label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.isPrimary} onChange={(event) => setForm({ ...form, isPrimary: event.target.checked })} /> Primary contact</label>
      <div className="flex gap-2 sm:justify-end"><button type="button" disabled={saving} onClick={() => void save()} className="inline-flex items-center gap-2 rounded-md bg-clinical-primary px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"><Plus size={16} />{saving ? 'Saving…' : editing ? 'Update' : 'Add contact'}</button>{editing ? <button type="button" disabled={saving} onClick={() => { setEditing(null); setForm(empty); }} className="rounded-md border px-3 py-2 text-sm">Cancel</button> : null}</div>
    </div>
    {error ? <p role="alert" className="mt-3 text-sm text-clinical-critical">{error}</p> : null}
  </section>;
}
