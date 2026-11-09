import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/utils/theme_ext.dart';

class SubscriptionScreen extends StatefulWidget {
  const SubscriptionScreen({super.key});

  @override
  State<SubscriptionScreen> createState() => _SubscriptionScreenState();
}

class _SubscriptionScreenState extends State<SubscriptionScreen> {
  int _currentPlan = 0; // 0=Free, 1=Premium, 2=VIP

  static const _plans = [
    _Plan(
      name: 'Standard',
      badge: 'Free',
      price: null,
      color: AppColors.accentGreen,
      description: 'Everything you need to get started.',
      features: [
        'Glucose logging',
        'Insuline logging',
        'Basic analytics',
        'Daily glucose trends',
        'community support',
      ],
    ),
    _Plan(
      name: 'Premium',
      badge: '349 EGP',
      price: '349 EGP / month',
      color: AppColors.primary,
      description: 'Advanced tools for better control.',
      features: [
        'Digital twin simulations',
        'Bolus recommendations',
        'Basal schedule optimization',
        '30 / 60 / 120 min glucose predictions',
        'what-if scenarios',
        'Personalized AI adaption',
      ],
    ),
    _Plan(
      name: 'Premium',
      badge: '599 EGP',
      price: '599 EGP / month',
      color: AppColors.accentPurple,
      description: 'Full digital twin — no limits.',
      features: [
        'Online doctor consultations & direct chat with assigned diabetes specialist',
        'Review of AI recommendations by doctor',
        'Monthly health assessment',
        'Emergency consultation requests',
        'Doctor-generated reports',
      ],
    ),
  ];

  void _selectPlan(int index) {
    if (index == _currentPlan) return;
    if (index == 0) {
      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          backgroundColor: context.cardBg,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(AppSpacing.radiusXl)),
          title: Text('Downgrade to Free',
              style: TextStyle(
                  color: context.textPri, fontWeight: FontWeight.w700)),
          content: Text(
            'You will lose access to premium features at the end of your current billing period.',
            style: TextStyle(color: context.textSec, fontSize: 13, height: 1.4),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: Text('Keep Plan',
                    style: TextStyle(color: context.textMut))),
            ElevatedButton(
              onPressed: () {
                Navigator.pop(ctx);
                setState(() => _currentPlan = 0);
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                      content: Text('Downgraded to Standard (Free)')),
                );
              },
              style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.danger,
                  foregroundColor: Colors.white),
              child: const Text('Downgrade'),
            ),
          ],
        ),
      );
      return;
    }
    _showPaymentDialog(index);
  }

  void _showPaymentDialog(int planIndex) {
    final plan = _plans[planIndex];
    final cardCtrl = TextEditingController();
    final expiryCtrl = TextEditingController();
    final cvvCtrl = TextEditingController();
    final nameCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: context.cardBg,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.radiusXl)),
        title: Row(children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: plan.color.withOpacity(0.12),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(Icons.workspace_premium_rounded,
                color: plan.color, size: 16),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text('Upgrade to ${plan.name}',
                style: TextStyle(
                    color: context.textPri,
                    fontWeight: FontWeight.w700,
                    fontSize: 16)),
          ),
        ]),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: plan.color.withOpacity(0.08),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: plan.color.withOpacity(0.2)),
                ),
                child: Row(children: [
                  Icon(Icons.info_outline_rounded, color: plan.color, size: 14),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text('You will be charged ${plan.price}.',
                        style: TextStyle(
                            color: plan.color,
                            fontSize: 12,
                            fontWeight: FontWeight.w500)),
                  ),
                ]),
              ),
              const SizedBox(height: 16),
              _payField(context, cardCtrl, 'Card Number',
                  Icons.credit_card_rounded, '1234 5678 9012 3456'),
              const SizedBox(height: 10),
              Row(children: [
                Expanded(
                    child: _payField(context, expiryCtrl, 'Expiry',
                        Icons.date_range_rounded, 'MM/YY')),
                const SizedBox(width: 10),
                Expanded(
                    child: _payField(
                        context, cvvCtrl, 'CVV', Icons.lock_rounded, '•••')),
              ]),
              const SizedBox(height: 10),
              _payField(context, nameCtrl, 'Cardholder Name',
                  Icons.person_rounded, 'Full name'),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: Text('Cancel', style: TextStyle(color: context.textMut))),
          ElevatedButton.icon(
            icon: const Icon(Icons.lock_rounded, size: 15),
            label: const Text('Pay & Upgrade',
                style: TextStyle(fontWeight: FontWeight.w600)),
            onPressed: () {
              Navigator.pop(ctx);
              setState(() => _currentPlan = planIndex);
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('Upgraded to ${plan.name}! 🎉'),
                  backgroundColor: plan.color,
                ),
              );
            },
            style: ElevatedButton.styleFrom(
                backgroundColor: plan.color, foregroundColor: Colors.white),
          ),
        ],
      ),
    );
  }

  Widget _payField(BuildContext context, TextEditingController ctrl,
      String label, IconData icon, String hint) {
    return TextField(
      controller: ctrl,
      style: TextStyle(color: context.textPri, fontSize: 13),
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        prefixIcon: Icon(icon, color: context.textMut, size: 18),
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
          borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        labelStyle: TextStyle(color: context.textMut, fontSize: 12),
        hintStyle: TextStyle(color: context.textMut, fontSize: 12),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.appBg,
      appBar: AppBar(
        backgroundColor: context.appBg,
        title: Text('Subscription Plans',
            style:
                TextStyle(color: context.textPri, fontWeight: FontWeight.w700)),
      ),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.screenPadding),
        children: [
          // Current plan badge
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: _plans[_currentPlan].color.withOpacity(0.08),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                  color: _plans[_currentPlan].color.withOpacity(0.3)),
            ),
            child: Row(children: [
              Icon(Icons.workspace_premium_rounded,
                  color: _plans[_currentPlan].color, size: 18),
              const SizedBox(width: 10),
              Text(
                'Current plan: ${_plans[_currentPlan].name} (${_plans[_currentPlan].price ?? 'Free'})',
                style: TextStyle(
                  color: _plans[_currentPlan].color,
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
            ]),
          ).animate().fadeIn(duration: 300.ms),

          const SizedBox(height: 20),

          ...List.generate(_plans.length, (i) {
            final plan = _plans[i];
            final isCurrent = i == _currentPlan;
            return Padding(
              padding: EdgeInsets.only(bottom: i < _plans.length - 1 ? 16 : 0),
              child: _PlanCard(
                plan: plan,
                isCurrent: isCurrent,
                onSelect: () => _selectPlan(i),
              )
                  .animate(delay: Duration(milliseconds: 80 + i * 80))
                  .fadeIn(duration: 400.ms)
                  .slideY(begin: 0.06, end: 0),
            );
          }),
        ],
      ),
    );
  }
}

class _Plan {
  const _Plan({
    required this.name,
    required this.badge,
    required this.price,
    required this.color,
    required this.description,
    required this.features,
  });
  final String name;
  final String badge;
  final String? price; // null = free
  final Color color;
  final String description;
  final List<String> features;
}

class _PlanCard extends StatelessWidget {
  const _PlanCard({
    required this.plan,
    required this.isCurrent,
    required this.onSelect,
  });
  final _Plan plan;
  final bool isCurrent;
  final VoidCallback onSelect;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onSelect,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: isCurrent ? plan.color.withOpacity(0.07) : context.cardBg,
          borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
          border: Border.all(
            color: isCurrent ? plan.color.withOpacity(0.5) : context.borderC,
            width: isCurrent ? 1.5 : 1,
          ),
          boxShadow: isCurrent
              ? [
                  BoxShadow(
                    color: plan.color.withOpacity(0.1),
                    blurRadius: 20,
                    offset: const Offset(0, 4),
                  ),
                ]
              : null,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Row(children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: plan.color.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(plan.name,
                    style: TextStyle(
                        color: plan.color,
                        fontWeight: FontWeight.w700,
                        fontSize: 14)),
              ),
              const SizedBox(width: 8),
              if (isCurrent)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: plan.color.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: const Text('Current',
                      style: TextStyle(
                          color: AppColors.accentGreen,
                          fontSize: 9,
                          fontWeight: FontWeight.w600)),
                ),
              const Spacer(),
              Text(
                plan.price ?? 'Free',
                style: TextStyle(
                    color: plan.color,
                    fontWeight: FontWeight.w700,
                    fontSize: 15),
              ),
            ]),

            const SizedBox(height: 6),
            Text(plan.description,
                style: TextStyle(
                    color: context.textSec, fontSize: 12, height: 1.4)),

            const SizedBox(height: 14),

            // Features
            ...plan.features.map((f) => Padding(
                  padding: const EdgeInsets.only(bottom: 7),
                  child: Row(children: [
                    Icon(Icons.check_circle_rounded,
                        color: plan.color, size: 14),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(f,
                          style:
                              TextStyle(color: context.textSec, fontSize: 12)),
                    ),
                  ]),
                )),

            // Button
            if (!isCurrent) ...[
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                height: 44,
                child: ElevatedButton(
                  onPressed: onSelect,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: plan.color,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                        borderRadius:
                            BorderRadius.circular(AppSpacing.radiusLg)),
                  ),
                  child: Text(
                    plan.price == null
                        ? 'Downgrade to Free'
                        : 'Upgrade to ${plan.name} — ${plan.price}',
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, fontSize: 13),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
