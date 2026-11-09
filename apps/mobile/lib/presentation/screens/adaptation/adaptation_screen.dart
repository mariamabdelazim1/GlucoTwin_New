import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:percent_indicator/circular_percent_indicator.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/navigation/route_names.dart';
import '../../widgets/common/gradient_button.dart';

class AdaptationScreen extends StatefulWidget {
  const AdaptationScreen({super.key});

  @override
  State<AdaptationScreen> createState() => _AdaptationScreenState();
}

class _AdaptationScreenState extends State<AdaptationScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.darkBackground,
      body: SafeArea(
        child: CustomScrollView(
          slivers: [
            SliverAppBar(
              pinned: true,
              backgroundColor: AppColors.darkBackground,
              title: const Text('Adaptation Phase',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              leading: IconButton(
                icon: const Icon(Icons.close_rounded),
                onPressed: () => context.go(RouteNames.home),
              ),
            ),
            SliverPadding(
              padding: const EdgeInsets.all(AppSpacing.screenPadding),
              sliver: SliverList(
                delegate: SliverChildListDelegate([
                  // Hero progress card
                  _ProgressHeroCard(pulse: _pulse)
                      .animate()
                      .fadeIn(duration: 500.ms),

                  const SizedBox(height: 24),

                  // Timeline
                  _AdaptationTimeline()
                      .animate(delay: 200.ms)
                      .fadeIn(duration: 400.ms),

                  const SizedBox(height: 24),

                  // Collection status
                  _DataCollectionCard()
                      .animate(delay: 300.ms)
                      .fadeIn(duration: 400.ms),

                  const SizedBox(height: 24),

                  // AI fine-tuning card
                  _AIFineTuningCard()
                      .animate(delay: 400.ms)
                      .fadeIn(duration: 400.ms),

                  const SizedBox(height: 32),

                  GradientButton(
                    label: 'Continue to Home',
                    onPressed: () => context.go(RouteNames.home),
                    icon: Icons.home_rounded,
                  ).animate(delay: 500.ms).fadeIn(),
                ]),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProgressHeroCard extends StatelessWidget {
  const _ProgressHeroCard({required this.pulse});

  final AnimationController pulse;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0D1A35), Color(0xFF0A1220)],
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusXxl),
        border: Border.all(color: AppColors.primary.withOpacity(0.3)),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withOpacity(0.1),
            blurRadius: 30,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(children: [
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              ShaderMask(
                shaderCallback: (b) => const LinearGradient(
                  colors: AppColors.cyanGradient,
                ).createShader(b),
                child: const Text(
                  'Personalizing Your\nDigital Twin',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                    height: 1.2,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                '6 days remaining',
                style: TextStyle(color: AppColors.textSecondaryDark, fontSize: 14),
              ),
            ]),
            const Spacer(),
            AnimatedBuilder(
              animation: pulse,
              builder: (_, __) => CircularPercentIndicator(
                radius: 48,
                lineWidth: 6,
                percent: 0.62,
                center: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text(
                    '62%',
                    style: TextStyle(
                      color: Color.lerp(AppColors.primary, AppColors.accentCyan, pulse.value)!,
                      fontSize: 16,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const Text(
                    'Ready',
                    style: TextStyle(color: AppColors.textMutedDark, fontSize: 9),
                  ),
                ]),
                progressColor: AppColors.primary,
                backgroundColor: AppColors.darkBorder,
                circularStrokeCap: CircularStrokeCap.round,
              ),
            ),
          ]),

          const SizedBox(height: 20),

          // Day markers
          Row(
            children: List.generate(14, (i) {
              final isPast = i < 8;
              final isCurrent = i == 8;
              return Expanded(
                child: Container(
                  height: 6,
                  margin: const EdgeInsets.symmetric(horizontal: 1.5),
                  decoration: BoxDecoration(
                    color: isPast
                        ? AppColors.primary
                        : isCurrent
                            ? AppColors.accentCyan
                            : AppColors.darkBorder,
                    borderRadius: BorderRadius.circular(3),
                  ),
                ),
              );
            }),
          ),

          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: const [
              Text('Day 1', style: TextStyle(color: AppColors.textMutedDark, fontSize: 10)),
              Text('Day 8 ← Today', style: TextStyle(color: AppColors.accentCyan, fontSize: 10)),
              Text('Day 14', style: TextStyle(color: AppColors.textMutedDark, fontSize: 10)),
            ],
          ),
        ],
      ),
    );
  }
}

class _AdaptationTimeline extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final milestones = [
      _Milestone(
        day: 'Day 1–3',
        title: 'Initial Calibration',
        desc: 'Collecting baseline CGM & insulin data',
        status: MilestoneStatus.complete,
      ),
      _Milestone(
        day: 'Day 4–6',
        title: 'Pattern Recognition',
        desc: 'Identifying meal & exercise responses',
        status: MilestoneStatus.complete,
      ),
      _Milestone(
        day: 'Day 7–9',
        title: 'Physiological Modeling',
        desc: 'Fitting ODE parameters to your data',
        status: MilestoneStatus.active,
      ),
      _Milestone(
        day: 'Day 10–12',
        title: 'AI Fine-tuning',
        desc: 'Training prediction models on your patterns',
        status: MilestoneStatus.pending,
      ),
      _Milestone(
        day: 'Day 13–14',
        title: 'Validation',
        desc: 'Safety checks & accuracy verification',
        status: MilestoneStatus.pending,
      ),
    ];

    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        color: AppColors.darkCard,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: AppColors.darkBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(children: [
            Icon(Icons.timeline_rounded, color: AppColors.primary, size: 18),
            SizedBox(width: 8),
            Text(
              'Adaptation Timeline',
              style: TextStyle(
                color: AppColors.textPrimaryDark,
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
          ]),
          const SizedBox(height: 20),
          ...milestones.asMap().entries.map((e) => _MilestoneRow(
                milestone: e.value,
                isLast: e.key == milestones.length - 1,
              )),
        ],
      ),
    );
  }
}

enum MilestoneStatus { complete, active, pending }

class _Milestone {
  const _Milestone({
    required this.day,
    required this.title,
    required this.desc,
    required this.status,
  });

  final String day;
  final String title;
  final String desc;
  final MilestoneStatus status;
}

class _MilestoneRow extends StatelessWidget {
  const _MilestoneRow({required this.milestone, required this.isLast});

  final _Milestone milestone;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    final color = switch (milestone.status) {
      MilestoneStatus.complete => AppColors.accentGreen,
      MilestoneStatus.active => AppColors.primary,
      MilestoneStatus.pending => AppColors.textMutedDark,
    };

    final icon = switch (milestone.status) {
      MilestoneStatus.complete => Icons.check_circle_rounded,
      MilestoneStatus.active => Icons.radio_button_checked_rounded,
      MilestoneStatus.pending => Icons.radio_button_unchecked_rounded,
    };

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            children: [
              Icon(icon, color: color, size: 20),
              if (!isLast)
                Expanded(
                  child: Container(
                    width: 2,
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    decoration: BoxDecoration(
                      color: AppColors.darkBorder,
                      borderRadius: BorderRadius.circular(1),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Text(
                      milestone.title,
                      style: TextStyle(
                        color: milestone.status == MilestoneStatus.pending
                            ? AppColors.textSecondaryDark
                            : AppColors.textPrimaryDark,
                        fontWeight: FontWeight.w600,
                        fontSize: 13,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: color.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        milestone.day,
                        style: TextStyle(color: color, fontSize: 9, fontWeight: FontWeight.w600),
                      ),
                    ),
                    if (milestone.status == MilestoneStatus.active) ...[
                      const SizedBox(width: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: AppColors.primary.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(4),
                          border: Border.all(color: AppColors.primary.withOpacity(0.3)),
                        ),
                        child: const Text(
                          'In Progress',
                          style: TextStyle(
                              color: AppColors.primary,
                              fontSize: 9,
                              fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ]),
                  const SizedBox(height: 2),
                  Text(
                    milestone.desc,
                    style: const TextStyle(
                      color: AppColors.textSecondaryDark,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _DataCollectionCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        color: AppColors.darkCard,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: AppColors.darkBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(children: [
            Icon(Icons.sensors_rounded, color: AppColors.accentCyan, size: 18),
            SizedBox(width: 8),
            Text(
              'Data Collection Status',
              style: TextStyle(
                color: AppColors.textPrimaryDark,
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
          ]),
          const SizedBox(height: 16),
          _CollectionItem(label: 'CGM Readings', collected: 2304, total: 4032, color: AppColors.accentCyan),
          const SizedBox(height: 10),
          _CollectionItem(label: 'Meal Events', collected: 45, total: 56, color: AppColors.accentGreen),
          const SizedBox(height: 10),
          _CollectionItem(label: 'Insulin Doses', collected: 58, total: 80, color: AppColors.accentPurple),
          const SizedBox(height: 10),
          _CollectionItem(label: 'Activity Data', collected: 1152, total: 2016, color: AppColors.primary),
        ],
      ),
    );
  }
}

class _CollectionItem extends StatelessWidget {
  const _CollectionItem({
    required this.label,
    required this.collected,
    required this.total,
    required this.color,
  });

  final String label;
  final int collected;
  final int total;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final pct = collected / total;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label,
                style: const TextStyle(
                    color: AppColors.textSecondaryDark, fontSize: 12)),
            Text(
              '$collected / $total',
              style: TextStyle(
                  color: color, fontSize: 11, fontWeight: FontWeight.w600),
            ),
          ],
        ),
        const SizedBox(height: 5),
        ClipRRect(
          borderRadius: BorderRadius.circular(6),
          child: LinearProgressIndicator(
            value: pct,
            backgroundColor: AppColors.darkBorder,
            valueColor: AlwaysStoppedAnimation(color),
            minHeight: 6,
          ),
        ),
      ],
    );
  }
}

class _AIFineTuningCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppColors.primary.withOpacity(0.1),
            AppColors.accentPurple.withOpacity(0.05),
          ],
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: AppColors.primary.withOpacity(0.25)),
      ),
      child: Row(
        children: [
          Container(
            width: 52,
            height: 52,
            decoration: BoxDecoration(
              gradient: const LinearGradient(colors: AppColors.primaryGradient),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Icon(Icons.model_training_rounded,
                color: Colors.white, size: 26),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'AI Model Training',
                  style: TextStyle(
                    color: AppColors.textPrimaryDark,
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Your model will begin fine-tuning on Day 10. Keep wearing your CGM for the best results.',
                  style: TextStyle(
                    color: AppColors.textSecondaryDark,
                    fontSize: 12,
                    height: 1.4,
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
