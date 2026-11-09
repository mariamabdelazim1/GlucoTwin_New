import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/utils/theme_ext.dart';

class _MedRecord {
  _MedRecord({
    required this.type,
    required this.title,
    required this.date,
    this.notes = '',
    List<String>? files,
  }) : files = files ?? [];
  final String type;
  final String title;
  final String date;
  final String notes;
  final List<String> files;
}

class MedicalHistoryScreen extends StatefulWidget {
  const MedicalHistoryScreen({super.key});

  @override
  State<MedicalHistoryScreen> createState() => _MedicalHistoryScreenState();
}

class _MedicalHistoryScreenState extends State<MedicalHistoryScreen> {
  final List<_MedRecord> _records = [
    _MedRecord(
      type: 'Diagnosis',
      title: 'Type 1 Diabetes Mellitus',
      date: 'Mar 2019',
      notes: 'Diagnosed at age 22 · Autoimmune (LADA excluded)',
      files: ['diagnosis_report_2019.pdf'],
    ),
    _MedRecord(
      type: 'Medication',
      title: 'Insulin Lispro (Humalog 100U/mL)',
      date: 'Mar 2019',
      notes: 'Rapid-acting · Bolus insulin',
    ),
    _MedRecord(
      type: 'Test',
      title: 'HbA1c — 7.2%',
      date: 'Nov 2025',
      notes: 'Within target range (< 7.5%)',
      files: ['hba1c_nov2025.pdf'],
    ),
    _MedRecord(
      type: 'Test',
      title: 'Thyroid Function (TSH: 2.1 mIU/L)',
      date: 'Nov 2025',
      notes: 'Normal range',
    ),
    _MedRecord(
      type: 'Allergy',
      title: 'Penicillin',
      date: 'Jan 2018',
      notes: 'Skin rash — documented at Al-Ahrar Hospital',
    ),
  ];

  static const _typeColors = {
    'Diagnosis': AppColors.danger,
    'Medication': AppColors.primary,
    'Test': AppColors.accentCyan,
    'Allergy': AppColors.warning,
    'Surgery': AppColors.accentPurple,
    'Vaccination': AppColors.accentGreen,
    'Other': AppColors.textMutedDark,
  };

  static const _typeIcons = {
    'Diagnosis': Icons.local_hospital_rounded,
    'Medication': Icons.medication_rounded,
    'Test': Icons.biotech_rounded,
    'Allergy': Icons.warning_amber_rounded,
    'Surgery': Icons.healing_rounded,
    'Vaccination': Icons.vaccines_rounded,
    'Other': Icons.notes_rounded,
  };

  static const _mockFiles = [
    'blood_test_results.pdf',
    'glucose_log_report.pdf',
    'doctor_prescription.pdf',
    'ecg_report.pdf',
    'lab_results_full.pdf',
    'eye_checkup_report.pdf',
  ];

  void _showAddDialog() {
    final titleCtrl = TextEditingController();
    final notesCtrl = TextEditingController();
    String selectedType = 'Test';
    final types = ['Diagnosis', 'Medication', 'Test', 'Allergy', 'Surgery', 'Vaccination', 'Other'];

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlg) => AlertDialog(
          backgroundColor: context.cardBg,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(AppSpacing.radiusXl)),
          title: Text('Add Medical Record',
              style: TextStyle(
                  color: context.textPri, fontWeight: FontWeight.w700)),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Record Type',
                    style: TextStyle(
                        color: context.textSec, fontSize: 12)),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: types.map((t) {
                    final sel = t == selectedType;
                    final c = _typeColors[t] ?? AppColors.textMutedDark;
                    return GestureDetector(
                      onTap: () => setDlg(() => selectedType = t),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 5),
                        decoration: BoxDecoration(
                          color: sel
                              ? c.withOpacity(0.15)
                              : context.appBg,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                            color: sel
                                ? c.withOpacity(0.5)
                                : context.borderC,
                          ),
                        ),
                        child: Text(t,
                            style: TextStyle(
                                color: sel ? c : context.textMut,
                                fontSize: 11,
                                fontWeight: FontWeight.w600)),
                      ),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: titleCtrl,
                  style: TextStyle(
                      color: context.textPri, fontSize: 14),
                  decoration: InputDecoration(
                    hintText: 'Title / description',
                    hintStyle: TextStyle(color: context.textMut),
                    filled: true,
                    fillColor: context.appBg,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide(color: context.borderC),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide(color: context.borderC),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: const BorderSide(
                          color: AppColors.primary, width: 1.5),
                    ),
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 12),
                  ),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: notesCtrl,
                  maxLines: 2,
                  style: TextStyle(
                      color: context.textPri, fontSize: 13),
                  decoration: InputDecoration(
                    hintText: 'Notes (optional)',
                    hintStyle: TextStyle(color: context.textMut),
                    filled: true,
                    fillColor: context.appBg,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide(color: context.borderC),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide(color: context.borderC),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: const BorderSide(
                          color: AppColors.primary, width: 1.5),
                    ),
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 12),
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: Text('Cancel',
                  style: TextStyle(color: context.textMut)),
            ),
            ElevatedButton(
              onPressed: () {
                if (titleCtrl.text.trim().isEmpty) return;
                Navigator.pop(ctx);
                setState(() {
                  _records.insert(
                    0,
                    _MedRecord(
                      type: selectedType,
                      title: titleCtrl.text.trim(),
                      date: _today(),
                      notes: notesCtrl.text.trim(),
                    ),
                  );
                });
              },
              style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  foregroundColor: Colors.white),
              child: const Text('Add'),
            ),
          ],
        ),
      ),
    );
  }

  void _showFilePickerFor(int index) {
    showModalBottomSheet(
      context: context,
      backgroundColor: context.cardBg,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
          borderRadius:
              BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) {
        final available = _mockFiles
            .where((f) => !_records[index].files.contains(f))
            .toList();
        return ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(ctx).size.height * 0.65,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
                child: Text('Select File to Upload',
                    style: TextStyle(
                        color: context.textPri,
                        fontWeight: FontWeight.w700,
                        fontSize: 16)),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Text('Tap a file to attach it to this record.',
                    style: TextStyle(
                        color: context.textSec, fontSize: 12)),
              ),
              const SizedBox(height: 8),
              if (available.isEmpty)
                Padding(
                  padding: const EdgeInsets.all(24),
                  child: Center(
                    child: Text('All files already attached.',
                        style: TextStyle(
                            color: context.textMut, fontSize: 13)),
                  ),
                )
              else
                Flexible(
                  child: ListView(
                    shrinkWrap: true,
                    children: available
                        .map((f) => ListTile(
                              leading: Container(
                                width: 36,
                                height: 36,
                                decoration: BoxDecoration(
                                  color: AppColors.danger
                                      .withOpacity(0.1),
                                  borderRadius:
                                      BorderRadius.circular(8),
                                ),
                                child: const Icon(
                                    Icons.picture_as_pdf_rounded,
                                    color: AppColors.danger,
                                    size: 18),
                              ),
                              title: Text(f,
                                  style: TextStyle(
                                      color: context.textPri,
                                      fontSize: 13,
                                      fontWeight: FontWeight.w500)),
                              subtitle: Text(
                                  '${(50 + _mockFiles.indexOf(f) * 37) % 400 + 50} KB',
                                  style: TextStyle(
                                      color: context.textMut,
                                      fontSize: 11)),
                              onTap: () {
                                Navigator.pop(ctx);
                                setState(() =>
                                    _records[index].files.add(f));
                                ScaffoldMessenger.of(context)
                                    .showSnackBar(SnackBar(
                                  content: Text('$f uploaded'),
                                  backgroundColor:
                                      AppColors.accentGreen,
                                ));
                              },
                            ))
                        .toList(),
                  ),
                ),
              const SizedBox(height: 16),
            ],
          ),
        );
      },
    );
  }

  String _today() {
    final now = DateTime.now();
    const months = [
      'Jan','Feb','Mar','Apr','May','Jun',
      'Jul','Aug','Sep','Oct','Nov','Dec'
    ];
    return '${months[now.month - 1]} ${now.year}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.appBg,
      appBar: AppBar(
        backgroundColor: context.appBg,
        title: Text('Medical History',
            style: TextStyle(
                color: context.textPri, fontWeight: FontWeight.w700)),
        actions: [
          TextButton.icon(
            icon: const Icon(Icons.add_rounded, size: 16),
            label: const Text('Add'),
            onPressed: _showAddDialog,
            style: TextButton.styleFrom(
                foregroundColor: AppColors.primary),
          ),
        ],
      ),
      body: _records.isEmpty
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.folder_open_rounded,
                      color: context.textMut, size: 48),
                  const SizedBox(height: 12),
                  Text('No records yet',
                      style: TextStyle(
                          color: context.textMut, fontSize: 14)),
                  const SizedBox(height: 8),
                  TextButton(
                    onPressed: _showAddDialog,
                    child: const Text('Add your first record'),
                  ),
                ],
              ),
            )
          : ListView.separated(
              padding: const EdgeInsets.all(AppSpacing.screenPadding),
              itemCount: _records.length,
              separatorBuilder: (_, __) =>
                  const SizedBox(height: 12),
              itemBuilder: (_, i) => _RecordCard(
                record: _records[i],
                typeColor: _typeColors[_records[i].type] ??
                    AppColors.textMutedDark,
                typeIcon: _typeIcons[_records[i].type] ??
                    Icons.notes_rounded,
                onDelete: () =>
                    setState(() => _records.removeAt(i)),
                onUpload: () => _showFilePickerFor(i),
                onRemoveFile: (f) =>
                    setState(() => _records[i].files.remove(f)),
              )
                  .animate(delay: Duration(milliseconds: i * 50))
                  .fadeIn(duration: 300.ms)
                  .slideY(begin: 0.05, end: 0),
            ),
    );
  }
}

class _RecordCard extends StatelessWidget {
  const _RecordCard({
    required this.record,
    required this.typeColor,
    required this.typeIcon,
    required this.onDelete,
    required this.onUpload,
    required this.onRemoveFile,
  });

  final _MedRecord record;
  final Color typeColor;
  final IconData typeIcon;
  final VoidCallback onDelete;
  final VoidCallback onUpload;
  final ValueChanged<String> onRemoveFile;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: context.cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: context.borderC),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: typeColor.withOpacity(0.12),
                borderRadius: BorderRadius.circular(11),
              ),
              child: Icon(typeIcon, color: typeColor, size: 18),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: typeColor.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(record.type,
                          style: TextStyle(
                              color: typeColor,
                              fontSize: 9,
                              fontWeight: FontWeight.w600)),
                    ),
                    const Spacer(),
                    Text(record.date,
                        style: TextStyle(
                            color: context.textMut, fontSize: 10)),
                    const SizedBox(width: 8),
                    GestureDetector(
                      onTap: onDelete,
                      child: Icon(Icons.close_rounded,
                          color: context.textMut, size: 16),
                    ),
                  ]),
                  const SizedBox(height: 5),
                  Text(record.title,
                      style: TextStyle(
                          color: context.textPri,
                          fontWeight: FontWeight.w600,
                          fontSize: 13)),
                  if (record.notes.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(record.notes,
                        style: TextStyle(
                            color: context.textMut,
                            fontSize: 11,
                            height: 1.3)),
                  ],
                ],
              ),
            ),
          ]),

          // Uploaded files
          if (record.files.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: record.files.map((f) {
                return Container(
                  padding: const EdgeInsets.fromLTRB(8, 5, 6, 5),
                  decoration: BoxDecoration(
                    color: AppColors.danger.withOpacity(0.08),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                        color: AppColors.danger.withOpacity(0.2)),
                  ),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    const Icon(Icons.picture_as_pdf_rounded,
                        color: AppColors.danger, size: 13),
                    const SizedBox(width: 5),
                    Text(f,
                        style: const TextStyle(
                            color: AppColors.danger,
                            fontSize: 10,
                            fontWeight: FontWeight.w500)),
                    const SizedBox(width: 5),
                    GestureDetector(
                      onTap: () => onRemoveFile(f),
                      child: const Icon(Icons.close_rounded,
                          color: AppColors.danger, size: 12),
                    ),
                  ]),
                );
              }).toList(),
            ),
          ],

          // Upload button
          const SizedBox(height: 10),
          GestureDetector(
            onTap: onUpload,
            child: Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color: context.appBg,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: context.borderC),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.upload_file_rounded,
                    color: context.textMut, size: 14),
                const SizedBox(width: 6),
                Text('Upload File',
                    style: TextStyle(
                        color: context.textSec,
                        fontSize: 11,
                        fontWeight: FontWeight.w500)),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}
