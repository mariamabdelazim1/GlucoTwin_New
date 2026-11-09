import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/navigation/route_names.dart';
import '../../../core/utils/theme_ext.dart';
import '../../providers/patient_provider.dart';
import '../../providers/theme_provider.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final patient = ref.watch(patientProvider);
    final themeNotifier = ref.read(themeProvider.notifier);
    final isDark = ref.watch(themeProvider) == ThemeMode.dark;

    return Scaffold(
      backgroundColor: context.appBg,
      body: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(
            child: _ProfileHeader(patient: patient)
                .animate()
                .fadeIn(duration: 400.ms),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.screenPadding, 20,
                AppSpacing.screenPadding, 100),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                _StatsRow(patient: patient)
                    .animate(delay: 100.ms)
                    .fadeIn(duration: 400.ms),
                const SizedBox(height: 28),

                _DeviceSection(patient: patient)
                    .animate(delay: 200.ms)
                    .fadeIn(duration: 400.ms),
                const SizedBox(height: 16),

                // Medical History → navigate to dedicated page
                _NavSectionButton(
                  icon: Icons.folder_shared_rounded,
                  title: 'Medical History',
                  subtitle: 'View tests, diagnoses & health records',
                  color: AppColors.accentAmber,
                  onTap: () => context.push(RouteNames.medicalHistory),
                ).animate(delay: 250.ms).fadeIn(duration: 400.ms),
                const SizedBox(height: 16),

                _SettingsSection(
                  isDark: isDark,
                  onThemeToggle: () => themeNotifier.toggle(),
                ).animate(delay: 300.ms).fadeIn(duration: 400.ms),
                const SizedBox(height: 16),

                _AccountSettingsSection()
                    .animate(delay: 350.ms)
                    .fadeIn(duration: 400.ms),
                const SizedBox(height: 16),

                _EmergencyContactSection()
                    .animate(delay: 370.ms)
                    .fadeIn(duration: 400.ms),
                const SizedBox(height: 16),

                // Subscription → navigate to dedicated page
                _NavSectionButton(
                  icon: Icons.workspace_premium_rounded,
                  title: 'Subscription',
                  subtitle: 'Standard (Free) · Manage your plan',
                  color: const Color(0xFFFFB800),
                  onTap: () => context.push(RouteNames.subscription),
                ).animate(delay: 380.ms).fadeIn(duration: 400.ms),
                const SizedBox(height: 16),

                _DangerSection()
                    .animate(delay: 420.ms)
                    .fadeIn(duration: 400.ms),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// NAV SECTION BUTTON
// ─────────────────────────────────────────────────────────────────────────────

class _NavSectionButton extends StatelessWidget {
  const _NavSectionButton({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.color,
    required this.onTap,
  });
  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: context.cardBg,
      borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        child: Container(
          padding: const EdgeInsets.all(AppSpacing.cardPadding),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
            border: Border.all(color: context.borderC),
          ),
          child: Row(children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: color.withOpacity(0.12),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: color, size: 22),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      color: context.textPri,
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: TextStyle(color: context.textMut, fontSize: 12),
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right_rounded,
                color: context.textMut, size: 22),
          ]),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// PROFILE HEADER  (always dark gradient — intentional brand look)
// ─────────────────────────────────────────────────────────────────────────────

class _ProfileHeader extends StatelessWidget {
  const _ProfileHeader({required this.patient});
  final patient;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.screenPadding, 60,
          AppSpacing.screenPadding, 24),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0D1A35), Color(0xFF070B14)],
        ),
      ),
      child: Column(
        children: [
          Container(
            width: 88,
            height: 88,
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                  colors: AppColors.primaryGradient),
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: AppColors.primary.withOpacity(0.4),
                  blurRadius: 24,
                  spreadRadius: 4,
                ),
              ],
            ),
            alignment: Alignment.center,
            child: Text(
              patient.avatarInitials,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 28,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            patient.name,
            style: const TextStyle(
              color: AppColors.textPrimaryDark,
              fontSize: 22,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: AppColors.accentGreen.withOpacity(0.12),
              borderRadius: BorderRadius.circular(100),
              border: Border.all(
                  color: AppColors.accentGreen.withOpacity(0.3)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.favorite_rounded,
                    color: AppColors.accentGreen, size: 14),
                const SizedBox(width: 6),
                Text(
                  'Avg Glucose: ${patient.avgGlucose.round()} mg/dL',
                  style: const TextStyle(
                    color: AppColors.accentGreen,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// STATS ROW
// ─────────────────────────────────────────────────────────────────────────────

class _StatsRow extends StatelessWidget {
  const _StatsRow({required this.patient});
  final patient;

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Expanded(
        child: _StatCard(
          label: 'TIR',
          value: '${patient.tir.round()}%',
          color: AppColors.accentGreen,
        ),
      ),
      const SizedBox(width: 10),
      Expanded(
        child: _StatCard(
          label: 'Avg Glucose',
          value: '${patient.avgGlucose.round()}',
          color: AppColors.accentCyan,
        ),
      ),
    ]);
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.label,
    required this.value,
    required this.color,
  });
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withOpacity(0.2)),
      ),
      child: Column(children: [
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          label,
          style: TextStyle(color: context.textMut, fontSize: 11),
        ),
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// DEVICE SECTION
// ─────────────────────────────────────────────────────────────────────────────

class _DeviceSection extends StatelessWidget {
  const _DeviceSection({required this.patient});
  final patient;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        color: context.cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: context.borderC),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeader(
            icon: Icons.devices_rounded,
            title: 'Connected Devices',
            color: AppColors.accentCyan,
          ),
          const SizedBox(height: 16),
          _DeviceRow(
            name: patient.cgmDevice,
            type: 'Continuous Glucose Monitor',
            icon: Icons.sensors_rounded,
            connected: patient.cgmConnected,
            color: AppColors.accentCyan,
            battery: 87,
          ),
          Divider(color: context.divC, height: 24),
          _DeviceRow(
            name: patient.pumpDevice,
            type: 'Insulin Delivery System',
            icon: Icons.vaccines_rounded,
            connected: patient.pumpConnected,
            color: AppColors.accentPurple,
            battery: 62,
          ),
          Divider(color: context.divC, height: 24),
          const _DeviceRow(
            name: 'Apple Watch Series 9',
            type: 'Smart Watch',
            icon: Icons.watch_rounded,
            connected: true,
            color: AppColors.accentGreen,
            battery: 78,
          ),
        ],
      ),
    );
  }
}

class _DeviceRow extends StatelessWidget {
  const _DeviceRow({
    required this.name,
    required this.type,
    required this.icon,
    required this.connected,
    required this.color,
    required this.battery,
  });
  final String name;
  final String type;
  final IconData icon;
  final bool connected;
  final Color color;
  final int battery;

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          color: color.withOpacity(0.12),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Icon(icon, color: color, size: 22),
      ),
      const SizedBox(width: 12),
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(
            name,
            style: TextStyle(
              color: context.textPri,
              fontWeight: FontWeight.w600,
              fontSize: 13,
            ),
          ),
          Text(type,
              style: TextStyle(color: context.textMut, fontSize: 11)),
        ]),
      ),
      Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
          decoration: BoxDecoration(
            color: connected
                ? AppColors.accentGreen.withOpacity(0.12)
                : AppColors.danger.withOpacity(0.12),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Text(
            connected ? 'Connected' : 'Offline',
            style: TextStyle(
              color: connected ? AppColors.accentGreen : AppColors.danger,
              fontSize: 10,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        const SizedBox(height: 3),
        Text(
          '🔋 $battery%',
          style: TextStyle(color: context.textMut, fontSize: 10),
        ),
      ]),
    ]);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// SETTINGS SECTION  (with real working bottom sheets)
// ─────────────────────────────────────────────────────────────────────────────

class _SettingsSection extends StatelessWidget {
  const _SettingsSection(
      {required this.isDark, required this.onThemeToggle});
  final bool isDark;
  final VoidCallback onThemeToggle;

  // ── Notifications sheet ──────────────────────────────────────────────────

  void _showNotificationsSheet(BuildContext context) {
    var pushEnabled = true;
    var emailAlerts = false;
    var criticalAlerts = true;
    var lowGlucoseAlerts = true;
    var weeklyReport = false;

    showModalBottomSheet(
      context: context,
      backgroundColor: context.cardBg,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius:
            BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            _sheetHandle(ctx),
            const SizedBox(height: 20),
            _sheetTitle(ctx, Icons.notifications_rounded,
                'Notification Settings', AppColors.primary),
            const SizedBox(height: 20),
            _SheetToggle(
              label: 'Push Notifications',
              icon: Icons.phone_android_rounded,
              value: pushEnabled,
              onChanged: (v) => setSt(() => pushEnabled = v),
            ),
            _SheetToggle(
              label: 'Email Alerts',
              icon: Icons.email_outlined,
              value: emailAlerts,
              onChanged: (v) => setSt(() => emailAlerts = v),
            ),
            _SheetToggle(
              label: 'Critical Alerts',
              icon: Icons.warning_amber_rounded,
              value: criticalAlerts,
              onChanged: (v) => setSt(() => criticalAlerts = v),
            ),
            _SheetToggle(
              label: 'Low Glucose Alerts',
              icon: Icons.trending_down_rounded,
              value: lowGlucoseAlerts,
              onChanged: (v) =>
                  setSt(() => lowGlucoseAlerts = v),
            ),
            _SheetToggle(
              label: 'Weekly Health Report',
              icon: Icons.summarize_rounded,
              value: weeklyReport,
              onChanged: (v) => setSt(() => weeklyReport = v),
              isLast: true,
            ),
          ]),
        ),
      ),
    );
  }

  // ── Glucose targets sheet ────────────────────────────────────────────────

  void _showGlucoseTargetsSheet(BuildContext context) {
    double lowTarget = 70;
    double highTarget = 180;

    showModalBottomSheet(
      context: context,
      backgroundColor: context.cardBg,
      shape: const RoundedRectangleBorder(
        borderRadius:
            BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            _sheetHandle(ctx),
            const SizedBox(height: 20),
            _sheetTitle(ctx, Icons.track_changes_rounded,
                'Glucose Targets', AppColors.accentCyan),
            const SizedBox(height: 24),

            // Low threshold
            Row(children: [
              const Icon(Icons.arrow_downward_rounded,
                  color: AppColors.accentCyan, size: 16),
              const SizedBox(width: 6),
              Text(
                'Low Alert Threshold',
                style: TextStyle(
                    color: ctx.textPri,
                    fontWeight: FontWeight.w600,
                    fontSize: 13),
              ),
              const Spacer(),
              Text(
                '${lowTarget.round()} mg/dL',
                style: const TextStyle(
                    color: AppColors.accentCyan,
                    fontWeight: FontWeight.w700,
                    fontSize: 14),
              ),
            ]),
            SliderTheme(
              data: SliderTheme.of(ctx).copyWith(
                activeTrackColor: AppColors.accentCyan,
                thumbColor: AppColors.accentCyan,
                inactiveTrackColor:
                    AppColors.accentCyan.withOpacity(0.2),
                overlayColor:
                    AppColors.accentCyan.withOpacity(0.1),
              ),
              child: Slider(
                value: lowTarget,
                min: 60,
                max: 100,
                divisions: 8,
                onChanged: (v) => setSt(() => lowTarget = v),
              ),
            ),
            const SizedBox(height: 8),

            // High threshold
            Row(children: [
              const Icon(Icons.arrow_upward_rounded,
                  color: AppColors.danger, size: 16),
              const SizedBox(width: 6),
              Text(
                'High Alert Threshold',
                style: TextStyle(
                    color: ctx.textPri,
                    fontWeight: FontWeight.w600,
                    fontSize: 13),
              ),
              const Spacer(),
              Text(
                '${highTarget.round()} mg/dL',
                style: const TextStyle(
                    color: AppColors.danger,
                    fontWeight: FontWeight.w700,
                    fontSize: 14),
              ),
            ]),
            SliderTheme(
              data: SliderTheme.of(ctx).copyWith(
                activeTrackColor: AppColors.danger,
                thumbColor: AppColors.danger,
                inactiveTrackColor:
                    AppColors.danger.withOpacity(0.2),
                overlayColor:
                    AppColors.danger.withOpacity(0.1),
              ),
              child: Slider(
                value: highTarget,
                min: 140,
                max: 300,
                divisions: 16,
                onChanged: (v) => setSt(() => highTarget = v),
              ),
            ),
            const SizedBox(height: 16),

            // Target range summary
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.accentGreen.withOpacity(0.08),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                    color: AppColors.accentGreen.withOpacity(0.2)),
              ),
              child: Row(children: [
                const Icon(Icons.check_circle_rounded,
                    color: AppColors.accentGreen, size: 16),
                const SizedBox(width: 8),
                Text(
                  'Target range: ${lowTarget.round()} – ${highTarget.round()} mg/dL',
                  style: const TextStyle(
                    color: AppColors.accentGreen,
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
              ]),
            ),
          ]),
        ),
      ),
    );
  }

  // ── Privacy & security sheet ─────────────────────────────────────────────

  void _showPrivacySheet(BuildContext context) {
    var anonymousData = false;
    var analytics = true;
    var biometric = false;
    var locationAccess = false;

    showModalBottomSheet(
      context: context,
      backgroundColor: context.cardBg,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius:
            BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSt) => SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            _sheetHandle(ctx),
            const SizedBox(height: 20),
            _sheetTitle(ctx, Icons.security_rounded,
                'Privacy & Security', AppColors.accentPurple),
            const SizedBox(height: 20),
            _SheetToggle(
              label: 'Share Anonymous Health Data',
              icon: Icons.share_rounded,
              value: anonymousData,
              onChanged: (v) => setSt(() => anonymousData = v),
            ),
            _SheetToggle(
              label: 'App Analytics',
              icon: Icons.analytics_outlined,
              value: analytics,
              onChanged: (v) => setSt(() => analytics = v),
            ),
            _SheetToggle(
              label: 'Biometric Login',
              icon: Icons.fingerprint_rounded,
              value: biometric,
              onChanged: (v) => setSt(() => biometric = v),
            ),
            _SheetToggle(
              label: 'Location Access',
              icon: Icons.location_on_outlined,
              value: locationAccess,
              onChanged: (v) => setSt(() => locationAccess = v),
              isLast: true,
            ),
          ]),
        ),
      ),
    );
  }

  // ── Help & support sheet ─────────────────────────────────────────────────

  void _showHelpSheet(BuildContext context) {
    const faqs = <_Faq>[
      _Faq(
        q: 'How does CGM sync work?',
        a: 'Your CGM device connects via Bluetooth and transmits glucose readings every 5 minutes. Make sure Bluetooth is enabled and the sensor is within 6 meters.',
      ),
      _Faq(
        q: 'How do I update my insulin settings?',
        a: 'Go to the What-If Simulator or the Bolus screen to adjust your insulin-to-carb ratio, sensitivity factor, and basal rates.',
      ),
      _Faq(
        q: 'What is the Digital Twin?',
        a: 'The digital twin is a personalised AI model of your glucose metabolism. It learns from your data to predict glucose trends and suggest optimal insulin doses.',
      ),
      _Faq(
        q: 'How accurate are the predictions?',
        a: 'Predictions improve over time as the AI adapts to your patterns. GlucoTwin targets a mean absolute error under 15 mg/dL at 30 minutes.',
      ),
    ];

    showModalBottomSheet(
      context: context,
      backgroundColor: context.cardBg,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius:
            BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.62,
        maxChildSize: 0.9,
        builder: (_, scrollCtrl) => ListView(
          controller: scrollCtrl,
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
          children: [
            Center(child: _sheetHandle(ctx)),
            const SizedBox(height: 20),
            _sheetTitle(ctx, Icons.help_outline_rounded,
                'Help & Support', AppColors.primary),
            const SizedBox(height: 20),
            ...faqs.map(
              (faq) => Theme(
                data: Theme.of(ctx)
                    .copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  title: Text(
                    faq.q,
                    style: TextStyle(
                      color: ctx.textPri,
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                    ),
                  ),
                  iconColor: AppColors.primary,
                  collapsedIconColor: ctx.textMut,
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(
                          16, 0, 16, 14),
                      child: Text(
                        faq.a,
                        style: TextStyle(
                          color: ctx.textSec,
                          fontSize: 12,
                          height: 1.5,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            Divider(color: ctx.divC),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              height: 44,
              child: ElevatedButton.icon(
                icon: const Icon(Icons.mail_outline_rounded,
                    size: 18),
                label: const Text('Contact Support'),
                onPressed: () {
                  Navigator.pop(ctx);
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                        content: Text('Opening support chat…')),
                  );
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(
                        AppSpacing.radiusLg),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: context.cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: context.borderC),
      ),
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.all(AppSpacing.cardPadding),
          child: _SectionHeader(
            icon: Icons.settings_rounded,
            title: 'Settings',
            color: AppColors.primary,
          ),
        ),
        Divider(height: 1, color: context.divC),
        _SettingsRow(
          icon: Icons.dark_mode_rounded,
          label: 'Dark Mode',
          trailing: Switch(
            value: isDark,
            onChanged: (_) => onThemeToggle(),
            activeColor: AppColors.primary,
          ),
        ),
        _SettingsRow(
          icon: Icons.notifications_rounded,
          label: 'Notifications',
          trailing: Icon(Icons.chevron_right_rounded,
              color: context.textMut),
          onTap: () => _showNotificationsSheet(context),
        ),
        _SettingsRow(
          icon: Icons.track_changes_rounded,
          label: 'Glucose Targets',
          trailing: Icon(Icons.chevron_right_rounded,
              color: context.textMut),
          onTap: () => _showGlucoseTargetsSheet(context),
        ),
        _SettingsRow(
          icon: Icons.security_rounded,
          label: 'Privacy & Security',
          trailing: Icon(Icons.chevron_right_rounded,
              color: context.textMut),
          onTap: () => _showPrivacySheet(context),
        ),
        _SettingsRow(
          icon: Icons.help_outline_rounded,
          label: 'Help & Support',
          trailing: Icon(Icons.chevron_right_rounded,
              color: context.textMut),
          isLast: true,
          onTap: () => _showHelpSheet(context),
        ),
      ]),
    );
  }
}

// Sheet helper widgets / functions

Widget _sheetHandle(BuildContext context) => Center(
      child: Container(
        width: 40,
        height: 4,
        decoration: BoxDecoration(
          color: context.borderC,
          borderRadius: BorderRadius.circular(2),
        ),
      ),
    );

Widget _sheetTitle(
    BuildContext context, IconData icon, String title, Color color) {
  return Row(children: [
    Icon(icon, color: color, size: 20),
    const SizedBox(width: 10),
    Text(
      title,
      style: TextStyle(
        color: context.textPri,
        fontWeight: FontWeight.w700,
        fontSize: 16,
      ),
    ),
  ]);
}

class _Faq {
  const _Faq({required this.q, required this.a});
  final String q;
  final String a;
}

class _SheetToggle extends StatelessWidget {
  const _SheetToggle({
    required this.label,
    required this.icon,
    required this.value,
    required this.onChanged,
    this.isLast = false,
  });
  final String label;
  final IconData icon;
  final bool value;
  final ValueChanged<bool> onChanged;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Row(children: [
          Icon(icon, color: context.textSec, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              label,
              style: TextStyle(color: context.textPri, fontSize: 14),
            ),
          ),
          Switch(
            value: value,
            onChanged: onChanged,
            activeColor: AppColors.primary,
          ),
        ]),
      ),
      if (!isLast) Divider(height: 1, color: context.divC),
    ]);
  }
}

class _SettingsRow extends StatelessWidget {
  const _SettingsRow({
    required this.icon,
    required this.label,
    required this.trailing,
    this.isLast = false,
    this.onTap,
  });
  final IconData icon;
  final String label;
  final Widget trailing;
  final bool isLast;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(
              horizontal: 16, vertical: 14),
          child: Row(children: [
            Icon(icon, color: context.textSec, size: 20),
            const SizedBox(width: 12),
            Text(
              label,
              style: TextStyle(
                  color: context.textPri, fontSize: 14),
            ),
            const Spacer(),
            trailing,
          ]),
        ),
      ),
      if (!isLast) Divider(height: 1, color: context.divC),
    ]);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// DANGER / SIGN OUT SECTION
// ─────────────────────────────────────────────────────────────────────────────

class _DangerSection extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        color: context.cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: context.borderC),
      ),
      child: Column(children: [
        _SectionHeader(
          icon: Icons.logout_rounded,
          title: 'Account',
          color: AppColors.danger,
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          height: 48,
          child: OutlinedButton.icon(
            icon: const Icon(Icons.logout_rounded, size: 18),
            label: const Text('Sign Out'),
            onPressed: () => context.go(RouteNames.login),
            style: OutlinedButton.styleFrom(
              foregroundColor: AppColors.danger,
              side: BorderSide(
                  color: AppColors.danger.withOpacity(0.4)),
              shape: RoundedRectangleBorder(
                borderRadius:
                    BorderRadius.circular(AppSpacing.radiusLg),
              ),
            ),
          ),
        ),
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION HEADER
// ─────────────────────────────────────────────────────────────────────────────

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({
    required this.icon,
    required this.title,
    required this.color,
  });
  final IconData icon;
  final String title;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Icon(icon, color: color, size: 18),
      const SizedBox(width: 8),
      Text(
        title,
        style: TextStyle(
          color: context.textPri,
          fontWeight: FontWeight.w600,
          fontSize: 14,
        ),
      ),
    ]);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// ACCOUNT SETTINGS
// ─────────────────────────────────────────────────────────────────────────────

class _AccountSettingsSection extends StatefulWidget {
  @override
  State<_AccountSettingsSection> createState() =>
      _AccountSettingsSectionState();
}

class _AccountSettingsSectionState
    extends State<_AccountSettingsSection> {
  bool _twoFactor = false;

  void _showChangePasswordDialog() {
    final current = TextEditingController();
    final newPass = TextEditingController();
    final confirm = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: context.cardBg,
        shape: RoundedRectangleBorder(
            borderRadius:
                BorderRadius.circular(AppSpacing.radiusXl)),
        title: Text(
          'Change Password',
          style: TextStyle(
            color: context.textPri,
            fontWeight: FontWeight.w700,
          ),
        ),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          _DialogField(
              controller: current,
              hint: 'Current password',
              obscure: true),
          const SizedBox(height: 12),
          _DialogField(
              controller: newPass,
              hint: 'New password',
              obscure: true),
          const SizedBox(height: 12),
          _DialogField(
              controller: confirm,
              hint: 'Confirm new password',
              obscure: true),
        ]),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text('Cancel',
                style: TextStyle(color: context.textMut)),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                    content: Text('Password updated successfully')),
              );
            },
            style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: Colors.white),
            child: const Text('Update'),
          ),
        ],
      ),
    );
  }

  void _showChangeEmailDialog() {
    final emailCtrl =
        TextEditingController(text: 'omar@example.com');
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: context.cardBg,
        shape: RoundedRectangleBorder(
            borderRadius:
                BorderRadius.circular(AppSpacing.radiusXl)),
        title: Text(
          'Change Email',
          style: TextStyle(
            color: context.textPri,
            fontWeight: FontWeight.w700,
          ),
        ),
        content: _DialogField(
            controller: emailCtrl, hint: 'New email address'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text('Cancel',
                style: TextStyle(color: context.textMut)),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                    content: Text('Verification email sent')),
              );
            },
            style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: Colors.white),
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: context.cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: context.borderC),
      ),
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.all(AppSpacing.cardPadding),
          child: _SectionHeader(
            icon: Icons.manage_accounts_rounded,
            title: 'Account Settings',
            color: AppColors.accentPurple,
          ),
        ),
        Divider(height: 1, color: context.divC),
        _SettingsRow(
          icon: Icons.lock_rounded,
          label: 'Change Password',
          trailing: Icon(Icons.chevron_right_rounded,
              color: context.textMut),
          onTap: _showChangePasswordDialog,
        ),
        _SettingsRow(
          icon: Icons.email_rounded,
          label: 'Change Email',
          trailing: Icon(Icons.chevron_right_rounded,
              color: context.textMut),
          onTap: _showChangeEmailDialog,
        ),
        _SettingsRow(
          icon: Icons.verified_user_rounded,
          label: 'Two-Factor Auth',
          trailing: Switch(
            value: _twoFactor,
            onChanged: (v) => setState(() => _twoFactor = v),
            activeColor: AppColors.primary,
          ),
        ),
        _SettingsRow(
          icon: Icons.download_rounded,
          label: 'Export Health Data',
          trailing: Icon(Icons.chevron_right_rounded,
              color: context.textMut),
          isLast: true,
          onTap: () => ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
                content: Text('Preparing your data export…')),
          ),
        ),
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// EMERGENCY CONTACT
// ─────────────────────────────────────────────────────────────────────────────

class _EmergencyContactSection extends StatefulWidget {
  @override
  State<_EmergencyContactSection> createState() =>
      _EmergencyContactSectionState();
}

class _EmergencyContactSectionState extends State<_EmergencyContactSection> {
  String _name = '';
  String _relationship = '';
  String _phone = '';

  void _showSheet() {
    final nameCtrl = TextEditingController(text: _name);
    final relCtrl = TextEditingController(text: _relationship);
    final phoneCtrl = TextEditingController(text: _phone);

    showModalBottomSheet(
      context: context,
      backgroundColor: context.cardBg,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => Padding(
        padding: EdgeInsets.fromLTRB(
            20, 16, 20, MediaQuery.of(ctx).viewInsets.bottom + 32),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          _sheetHandle(ctx),
          const SizedBox(height: 20),
          _sheetTitle(ctx, Icons.contact_phone_rounded,
              'Emergency Contact', AppColors.danger),
          const SizedBox(height: 20),
          _DialogField(controller: nameCtrl, hint: 'Contact name'),
          const SizedBox(height: 12),
          _DialogField(controller: relCtrl, hint: 'Relationship (e.g. Spouse)'),
          const SizedBox(height: 12),
          _DialogField(
              controller: phoneCtrl,
              hint: 'Phone number',
              keyboardType: TextInputType.phone),
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton(
              onPressed: () {
                setState(() {
                  _name = nameCtrl.text.trim();
                  _relationship = relCtrl.text.trim();
                  _phone = phoneCtrl.text.trim();
                });
                Navigator.pop(ctx);
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppSpacing.radiusLg)),
              ),
              child: const Text('Save'),
            ),
          ),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final hasContact = _name.isNotEmpty;
    return Material(
      color: context.cardBg,
      borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
      child: InkWell(
        onTap: _showSheet,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        child: Container(
          padding: const EdgeInsets.all(AppSpacing.cardPadding),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
            border: Border.all(color: context.borderC),
          ),
          child: Row(children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: AppColors.danger.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.contact_phone_rounded,
                  color: AppColors.danger, size: 22),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Emergency Contact',
                    style: TextStyle(
                      color: context.textPri,
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    hasContact
                        ? '$_name · $_relationship · $_phone'
                        : 'Tap to add an emergency contact',
                    style: TextStyle(color: context.textMut, fontSize: 12),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right_rounded,
                color: context.textMut, size: 22),
          ]),
        ),
      ),
    );
  }
}

class _DialogField extends StatelessWidget {
  const _DialogField({
    required this.controller,
    required this.hint,
    this.obscure = false,
    this.keyboardType,
  });
  final TextEditingController controller;
  final String hint;
  final bool obscure;
  final TextInputType? keyboardType;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      obscureText: obscure,
      keyboardType: keyboardType,
      style: TextStyle(color: context.textPri, fontSize: 14),
      decoration: InputDecoration(
        hintText: hint,
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
          borderSide:
              const BorderSide(color: AppColors.primary, width: 1.5),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      ),
    );
  }
}
