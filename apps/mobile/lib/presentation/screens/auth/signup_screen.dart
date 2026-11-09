import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/navigation/route_names.dart';
import '../../../core/utils/theme_ext.dart';
import '../../widgets/common/gradient_button.dart';

class SignupScreen extends StatefulWidget {
  const SignupScreen({super.key});

  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  int _step = 0;

  final _steps = ['Account Info', 'Medical Profile', 'Device Setup'];

  @override
  void dispose() {
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _passCtrl.dispose();
    super.dispose();
  }

  void _next() {
    if (_step == 0) {
      if (!_formKey.currentState!.validate()) return;
    }
    if (_step < 2) {
      setState(() => _step++);
    } else {
      setState(() => _loading = true);
      Future.delayed(const Duration(milliseconds: 1500), () {
        if (mounted) context.go(RouteNames.home);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.appBg,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_rounded),
          onPressed: () {
            if (_step > 0) {
              setState(() => _step--);
            } else {
              context.go(RouteNames.login);
            }
          },
        ),
        title: Text(
          _steps[_step],
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Text(
              '${_step + 1}/3',
              style: TextStyle(color: context.textSec),
            ),
          ),
        ],
      ),
      body: Form(
        key: _formKey,
        child: Column(
          children: [
            // Progress bar
            LinearProgressIndicator(
              value: (_step + 1) / 3,
              backgroundColor: context.borderC,
              valueColor: const AlwaysStoppedAnimation(AppColors.primary),
              minHeight: 3,
            ),

            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(AppSpacing.screenPadding),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 12),
                    AnimatedSwitcher(
                      duration: const Duration(milliseconds: 350),
                      transitionBuilder: (child, anim) => SlideTransition(
                        position: Tween(
                          begin: const Offset(0.3, 0),
                          end: Offset.zero,
                        ).animate(anim),
                        child: FadeTransition(opacity: anim, child: child),
                      ),
                      child: [
                        _AccountStep(
                          key: const ValueKey(0),
                          nameCtrl: _nameCtrl,
                          emailCtrl: _emailCtrl,
                          passCtrl: _passCtrl,
                          obscure: _obscure,
                          onToggleObscure: () =>
                              setState(() => _obscure = !_obscure),
                        ),
                        const _MedicalStep(key: ValueKey(1)),
                        const _DeviceStep(key: ValueKey(2)),
                      ][_step],
                    ),

                    const SizedBox(height: 32),

                    GradientButton(
                      label: _step < 2 ? 'Continue' : 'Create Account',
                      onPressed: _next,
                      isLoading: _loading,
                      icon: _step < 2
                          ? Icons.arrow_forward_rounded
                          : Icons.check_circle_rounded,
                    ).animate().fadeIn(duration: 300.ms),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 1 — ACCOUNT INFO
// ─────────────────────────────────────────────────────────────────────────────

class _AccountStep extends StatefulWidget {
  const _AccountStep({
    super.key,
    required this.nameCtrl,
    required this.emailCtrl,
    required this.passCtrl,
    required this.obscure,
    required this.onToggleObscure,
  });

  final TextEditingController nameCtrl;
  final TextEditingController emailCtrl;
  final TextEditingController passCtrl;
  final bool obscure;
  final VoidCallback onToggleObscure;

  @override
  State<_AccountStep> createState() => _AccountStepState();
}

class _AccountStepState extends State<_AccountStep> {
  String _gender = 'Male';
  DateTime? _dob;
  final _phoneCtrl = TextEditingController();
  final _emergencyNameCtrl = TextEditingController();
  final _emergencyPhoneCtrl = TextEditingController();

  static const _genderOptions = ['Male', 'Female'];

  @override
  void dispose() {
    _phoneCtrl.dispose();
    _emergencyNameCtrl.dispose();
    _emergencyPhoneCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime(1995),
      firstDate: DateTime(1920),
      lastDate: DateTime.now(),
      builder: (ctx, child) => Theme(
        data: Theme.of(ctx).copyWith(
          colorScheme: Theme.of(ctx).colorScheme.copyWith(
            primary: AppColors.primary,
          ),
        ),
        child: child!,
      ),
    );
    if (picked != null) setState(() => _dob = picked);
  }

  String _formatDate(DateTime? d) {
    if (d == null) return 'Select date of birth';
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    return '${d.day} ${months[d.month - 1]} ${d.year}';
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Create your\nGlucoTwin account',
          style: TextStyle(
            color: context.textPri,
            fontSize: 26,
            fontWeight: FontWeight.w800,
            height: 1.2,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Your digital twin journey starts here.',
          style: TextStyle(color: context.textSec, fontSize: 14),
        ),
        const SizedBox(height: 32),

        // Full Name
        TextFormField(
          controller: widget.nameCtrl,
          decoration: const InputDecoration(
            labelText: 'Full Name',
            prefixIcon: Icon(Icons.person_outline_rounded),
          ),
          validator: (val) {
            if (val == null || val.trim().isEmpty) return 'Full name is required';
            if (val.trim().length < 2) return 'Name must be at least 2 characters';
            return null;
          },
        ),
        const SizedBox(height: 16),

        // Email
        TextFormField(
          controller: widget.emailCtrl,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(
            labelText: 'Email Address',
            prefixIcon: Icon(Icons.mail_outline_rounded),
          ),
          validator: (val) {
            if (val == null || val.trim().isEmpty) return 'Email is required';
            final emailRegex = RegExp(r'^[\w\-.]+@([\w\-]+\.)+[\w]{2,}$');
            if (!emailRegex.hasMatch(val.trim())) {
              return 'Enter a valid email address';
            }
            return null;
          },
        ),
        const SizedBox(height: 16),

        // Password
        TextFormField(
          controller: widget.passCtrl,
          obscureText: widget.obscure,
          decoration: InputDecoration(
            labelText: 'Password',
            prefixIcon: const Icon(Icons.lock_outline_rounded),
            suffixIcon: IconButton(
              icon: Icon(
                widget.obscure
                    ? Icons.visibility_off_rounded
                    : Icons.visibility_rounded,
              ),
              onPressed: widget.onToggleObscure,
            ),
          ),
          validator: (val) {
            if (val == null || val.isEmpty) return 'Password is required';
            if (val.length < 8) return 'Password must be at least 8 characters';
            if (!val.contains(RegExp(r'[0-9]'))) {
              return 'Password must contain at least one number';
            }
            return null;
          },
        ),
        const SizedBox(height: 16),

        // Phone Number
        TextFormField(
          controller: _phoneCtrl,
          keyboardType: TextInputType.phone,
          decoration: const InputDecoration(
            labelText: 'Phone Number',
            prefixIcon: Icon(Icons.phone_outlined),
          ),
        ),
        const SizedBox(height: 24),

        // Gender
        Text(
          'Gender',
          style: TextStyle(
              color: context.textSec,
              fontSize: 13,
              fontWeight: FontWeight.w500),
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: _genderOptions.map((g) {
            final sel = g == _gender;
            return GestureDetector(
              onTap: () => setState(() => _gender = g),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: sel
                      ? AppColors.primary.withValues(alpha: 0.15)
                      : context.cardBg,
                  borderRadius: BorderRadius.circular(100),
                  border: Border.all(
                    color: sel
                        ? AppColors.primary.withValues(alpha: 0.6)
                        : context.borderC,
                  ),
                ),
                child: Text(
                  g,
                  style: TextStyle(
                    color: sel ? AppColors.primary : context.textSec,
                    fontSize: 13,
                    fontWeight: sel ? FontWeight.w600 : FontWeight.w400,
                  ),
                ),
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: 24),

        // Date of Birth
        Text(
          'Date of Birth',
          style: TextStyle(
              color: context.textSec,
              fontSize: 13,
              fontWeight: FontWeight.w500),
        ),
        const SizedBox(height: 10),
        GestureDetector(
          onTap: _pickDate,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
            decoration: BoxDecoration(
              color: context.cardBg,
              borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
              border: Border.all(color: context.borderC),
            ),
            child: Row(children: [
              Icon(Icons.calendar_today_rounded,
                  color: context.textMut, size: 18),
              const SizedBox(width: 10),
              Text(
                _formatDate(_dob),
                style: TextStyle(
                  color: _dob != null ? context.textPri : context.textMut,
                  fontSize: 14,
                ),
              ),
            ]),
          ),
        ),
        const SizedBox(height: 28),

        // Emergency Contact
        Text(
          'Emergency Contact',
          style: TextStyle(
              color: context.textSec,
              fontSize: 13,
              fontWeight: FontWeight.w500),
        ),
        const SizedBox(height: 10),
        TextFormField(
          controller: _emergencyNameCtrl,
          decoration: const InputDecoration(
            labelText: 'Contact Name',
            prefixIcon: Icon(Icons.contact_phone_outlined),
          ),
        ),
        const SizedBox(height: 12),
        TextFormField(
          controller: _emergencyPhoneCtrl,
          keyboardType: TextInputType.phone,
          decoration: const InputDecoration(
            labelText: 'Contact Phone Number',
            prefixIcon: Icon(Icons.phone_outlined),
          ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 2 — MEDICAL PROFILE
// ─────────────────────────────────────────────────────────────────────────────

class _MedicalStep extends StatefulWidget {
  const _MedicalStep({super.key});

  @override
  State<_MedicalStep> createState() => _MedicalStepState();
}

class _MedicalStepState extends State<_MedicalStep> {
  int _diagnosisYear = 2015;
  double _weight = 70;
  double _height = 170;
  int _targetLow = 70;
  int _targetHigh = 180;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Your medical\nprofile',
          style: TextStyle(
            color: context.textPri,
            fontSize: 26,
            fontWeight: FontWeight.w800,
            height: 1.2,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'This helps calibrate your digital twin.',
          style: TextStyle(color: context.textSec, fontSize: 14),
        ),
        const SizedBox(height: 32),
        _LabeledSlider(
          label: 'Diagnosis Year',
          value: _diagnosisYear.toDouble(),
          min: 1980,
          max: 2024,
          displayValue: '$_diagnosisYear',
          onChanged: (v) => setState(() => _diagnosisYear = v.round()),
        ),
        const SizedBox(height: 20),
        _LabeledSlider(
          label: 'Weight',
          value: _weight,
          min: 40,
          max: 150,
          displayValue: '${_weight.round()} kg',
          onChanged: (v) => setState(() => _weight = v),
        ),
        const SizedBox(height: 20),
        _LabeledSlider(
          label: 'Height',
          value: _height,
          min: 140,
          max: 210,
          displayValue: '${_height.round()} cm',
          onChanged: (v) => setState(() => _height = v),
        ),
        const SizedBox(height: 20),
        Row(children: [
          Expanded(
            child: _LabeledSlider(
              label: 'Target Low',
              value: _targetLow.toDouble(),
              min: 60,
              max: 90,
              displayValue: '$_targetLow',
              onChanged: (v) => setState(() => _targetLow = v.round()),
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: _LabeledSlider(
              label: 'Target High',
              value: _targetHigh.toDouble(),
              min: 140,
              max: 200,
              displayValue: '$_targetHigh',
              onChanged: (v) => setState(() => _targetHigh = v.round()),
            ),
          ),
        ]),
      ],
    );
  }
}

class _LabeledSlider extends StatelessWidget {
  const _LabeledSlider({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.displayValue,
    required this.onChanged,
  });

  final String label;
  final double value;
  final double min;
  final double max;
  final String displayValue;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label,
                style: TextStyle(color: context.textSec, fontSize: 13)),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: AppColors.primary.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                displayValue,
                style: const TextStyle(
                  color: AppColors.primary,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
        Slider(value: value, min: min, max: max, onChanged: onChanged),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// STEP 3 — DEVICE SETUP
// ─────────────────────────────────────────────────────────────────────────────

class _DeviceStep extends StatefulWidget {
  const _DeviceStep({super.key});

  @override
  State<_DeviceStep> createState() => _DeviceStepState();
}

class _DeviceStepState extends State<_DeviceStep> {
  String? _cgm = 'Dexcom G7';
  String? _pump = 'Omnipod 5';
  String? _watch = 'Apple Watch';

  final _cgmOptions = ['Dexcom G7', 'Libre 3', 'Medtronic CGM'];
  final _pumpOptions = [
    'Omnipod 5',
    'Tandem t:slim X2',
    'Medtronic 780G',
  ];
  final _watchOptions = [
    'Apple Watch',
    'Samsung Galaxy Watch',
    'Garmin',
    'None',
  ];

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Connect your\ndevices',
          style: TextStyle(
            color: context.textPri,
            fontSize: 26,
            fontWeight: FontWeight.w800,
            height: 1.2,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Select your CGM, insulin pump, and wearable devices.',
          style: TextStyle(color: context.textSec, fontSize: 14),
        ),
        const SizedBox(height: 32),
        _DeviceSelector(
          title: 'CGM Device',
          icon: Icons.sensors_rounded,
          color: AppColors.accentCyan,
          options: _cgmOptions,
          selected: _cgm,
          onSelect: (v) => setState(() => _cgm = v),
        ),
        const SizedBox(height: 20),
        _DeviceSelector(
          title: 'Insulin Pump',
          icon: Icons.vaccines_rounded,
          color: AppColors.accentPurple,
          options: _pumpOptions,
          selected: _pump,
          onSelect: (v) => setState(() => _pump = v),
        ),
        const SizedBox(height: 20),
        _DeviceSelector(
          title: 'Smart Watch',
          icon: Icons.watch_rounded,
          color: AppColors.accentGreen,
          options: _watchOptions,
          selected: _watch,
          onSelect: (v) => setState(() => _watch = v),
        ),
      ],
    );
  }
}

class _DeviceSelector extends StatelessWidget {
  const _DeviceSelector({
    required this.title,
    required this.icon,
    required this.color,
    required this.options,
    required this.selected,
    required this.onSelect,
  });

  final String title;
  final IconData icon;
  final Color color;
  final List<String> options;
  final String? selected;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          Icon(icon, color: color, size: 18),
          const SizedBox(width: 8),
          Text(title,
              style: TextStyle(
                  color: context.textPri, fontWeight: FontWeight.w600)),
        ]),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: options.map((o) {
            final isSelected = o == selected;
            return GestureDetector(
              onTap: () => onSelect(o),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: isSelected
                      ? color.withValues(alpha: 0.15)
                      : context.cardBg,
                  borderRadius: BorderRadius.circular(100),
                  border: Border.all(
                    color: isSelected
                        ? color.withValues(alpha: 0.6)
                        : context.borderC,
                  ),
                ),
                child: Text(
                  o,
                  style: TextStyle(
                    color: isSelected ? color : context.textSec,
                    fontSize: 13,
                    fontWeight:
                        isSelected ? FontWeight.w600 : FontWeight.w400,
                  ),
                ),
              ),
            );
          }).toList(),
        ),
      ],
    );
  }
}
