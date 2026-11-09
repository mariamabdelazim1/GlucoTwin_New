import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mergePublicDoctors } from './accountState.ts';

test('authoritative public doctor fields replace seeded values without overwriting local credentials', () => {
  const local = [{
    id: 'DR-001', role: 'doctor', email: 'doctor@example.test', password: 'local-only-password',
    doctorProfile: { fullName: 'Seed Name', specialty: 'Seed specialty', yearsExperience: '1', medicalSchool: 'Seed school', qualifications: 'Seed qualification', bio: 'Old bio', certificates: [], papers: [] },
  }];
  const remote = [{
    id: 'DR-001', role: 'doctor', email: 'doctor@example.test',
    doctorProfile: { fullName: 'Server Name', specialty: 'Endocrinology', yearsExperience: '12', medicalSchool: 'Server school', qualifications: 'Server qualification', bio: 'New biography', certificates: ['Server certificate'], papers: ['Server paper'], photo: 'server-photo', documents: [] },
  }];
  const merged = mergePublicDoctors(local, remote);
  assert.equal(merged[0].password, 'local-only-password');
  assert.deepEqual(merged[0].doctorProfile, remote[0].doctorProfile);
});

test('unchanged public doctors keep the same array and new doctors contain no credentials', () => {
  const local = [{ id: 'DR-001', role: 'doctor', email: 'one@example.test', password: 'password', doctorProfile: { fullName: 'One', specialty: '', yearsExperience: '', medicalSchool: '', qualifications: '', bio: '', certificates: [], papers: [] } }];
  const same = [{ id: 'DR-001', role: 'doctor', email: 'one@example.test', doctorProfile: local[0].doctorProfile }];
  assert.equal(mergePublicDoctors(local, same), local);
  const added = mergePublicDoctors(local, [...same, { id: 'DR-002', role: 'doctor', email: 'two@example.test', doctorProfile: { ...local[0].doctorProfile, fullName: 'Two' } }]);
  assert.equal(added[1].password, '');
});
