import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:smooth_page_indicator/smooth_page_indicator.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/navigation/route_names.dart';
import '../../../core/utils/theme_ext.dart';
import '../../widgets/common/gradient_button.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _controller = PageController();
  int _page = 0;

  static const _pages = [
    _OnboardingPage(
      title: 'Your Personal\nDigital Twin',
      subtitle:
          'GlucoTwin creates a physiological model of you — a living AI replica that learns your unique metabolism, predicts glucose 2 hours ahead, and keeps you safe.',
      color: AppColors.primary,
      accentColor: AppColors.accentCyan,
      icon: Icons.hub_rounded,
    ),
    _OnboardingPage(
      title: 'Predict Glucose\nBefore It Happens',
      subtitle:
          'Our AI continuously models your body response and warns you of lows and highs before your CGM detects them — giving you time to act.',
      color: AppColors.accentCyan,
      accentColor: AppColors.primary,
      icon: Icons.show_chart_rounded,
    ),
    _OnboardingPage(
      title: 'Smart Insulin\nRecommendations',
      subtitle:
          'Every bolus and basal suggestion is safety-simulated on your digital twin before being shown to you. No guesswork — just precision.',
      color: AppColors.accentPurple,
      accentColor: AppColors.primary,
      icon: Icons.vaccines_rounded,
    ),
    _OnboardingPage(
      title: 'Eat Confidently\nWith AI Guidance',
      subtitle:
          'Get personalized portion sizes, carb estimates, and glycemic impact forecasts for every meal — tailored to your exact physiology.',
      color: AppColors.accentGreen,
      accentColor: AppColors.accentCyan,
      icon: Icons.restaurant_rounded,
    ),
  ];

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _next() {
    if (_page < _pages.length - 1) {
      _controller.nextPage(
        duration: const Duration(milliseconds: 400),
        curve: Curves.easeOutCubic,
      );
    } else {
      context.go(RouteNames.login);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.appBg,
      body: Stack(
        children: [
          PageView.builder(
            controller: _controller,
            onPageChanged: (i) => setState(() => _page = i),
            itemCount: _pages.length,
            itemBuilder: (ctx, i) =>
                _OnboardingPageView(page: _pages[i], index: i),
          ),

          // Bottom controls
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.screenPadding,
                  0,
                  AppSpacing.screenPadding,
                  24,
                ),
                child: Column(
                  children: [
                    SmoothPageIndicator(
                      controller: _controller,
                      count: _pages.length,
                      effect: WormEffect(
                        dotHeight: 8,
                        dotWidth: 8,
                        activeDotColor: _pages[_page].color,
                        dotColor: context.borderC,
                        spacing: 10,
                      ),
                    ),
                    const SizedBox(height: 28),
                    GradientButton(
                      label: _page < _pages.length - 1
                          ? 'Continue'
                          : 'Get Started',
                      gradient: [
                        _pages[_page].color,
                        _pages[_page].accentColor
                      ],
                      onPressed: _next,
                      icon: _page < _pages.length - 1
                          ? Icons.arrow_forward_rounded
                          : Icons.rocket_launch_rounded,
                    ),
                    if (_page < _pages.length - 1) ...[
                      const SizedBox(height: 12),
                      TextButton(
                        onPressed: () => context.go(RouteNames.login),
                        child: Text(
                          'Skip for now',
                          style: TextStyle(color: context.textMut),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _OnboardingPage {
  const _OnboardingPage({
    required this.title,
    required this.subtitle,
    required this.color,
    required this.accentColor,
    required this.icon,
  });

  final String title;
  final String subtitle;
  final Color color;
  final Color accentColor;
  final IconData icon;
}

class _OnboardingPageView extends StatelessWidget {
  const _OnboardingPageView(
      {required this.page, required this.index});

  final _OnboardingPage page;
  final int index;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.screenPadding,
        0,
        AppSpacing.screenPadding,
        180,
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: _Illustration(page: page)
                .animate(key: ValueKey(index))
                .fadeIn(duration: 500.ms)
                .scale(
                  begin: const Offset(0.8, 0.8),
                  end: const Offset(1.0, 1.0),
                  duration: 600.ms,
                  curve: Curves.easeOutBack,
                ),
          ),

          const SizedBox(height: 48),

          Text(
            page.title,
            style: TextStyle(
              color: context.textPri,
              fontSize: 32,
              fontWeight: FontWeight.w800,
              height: 1.15,
              letterSpacing: -0.8,
            ),
          )
              .animate(key: ValueKey('title_$index'))
              .fadeIn(duration: 400.ms, delay: 100.ms)
              .slideX(begin: 0.2, end: 0, duration: 400.ms),

          const SizedBox(height: 16),

          Text(
            page.subtitle,
            style: TextStyle(
              color: context.textSec,
              fontSize: 15,
              height: 1.6,
            ),
          )
              .animate(key: ValueKey('sub_$index'))
              .fadeIn(duration: 400.ms, delay: 200.ms)
              .slideX(begin: 0.2, end: 0, duration: 400.ms),
        ],
      ),
    );
  }
}

class _Illustration extends StatelessWidget {
  const _Illustration({required this.page});

  final _OnboardingPage page;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 240,
      height: 240,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Container(
            width: 220,
            height: 220,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [
                  page.color.withValues(alpha: 0.15),
                  page.accentColor.withValues(alpha: 0.05),
                  Colors.transparent,
                ],
              ),
            ),
          ),

          Container(
            width: 160,
            height: 160,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(
                color: page.color.withValues(alpha: 0.2),
                width: 1.5,
              ),
            ),
          ),

          Container(
            width: 100,
            height: 100,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [page.color, page.accentColor],
              ),
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: page.color.withValues(alpha: 0.5),
                  blurRadius: 30,
                  spreadRadius: 5,
                ),
              ],
            ),
            child:
                Icon(page.icon, color: Colors.white, size: 46),
          ),

          ...List.generate(
            4,
            (i) => _OrbitDot(
              angle: i * 90.0,
              radius: 80,
              color: i.isEven ? page.color : page.accentColor,
            ),
          ),
        ],
      ),
    );
  }
}

class _OrbitDot extends StatelessWidget {
  const _OrbitDot({
    required this.angle,
    required this.radius,
    required this.color,
  });

  final double angle;
  final double radius;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Transform(
      transform: Matrix4.translationValues(
        radius *
            (angle == 0
                ? 1
                : angle == 90
                    ? 0
                    : angle == 180
                        ? -1
                        : 0),
        radius * (angle == 90 ? 1 : angle == 270 ? -1 : 0),
        0,
      ),
      child: Container(
        width: 8,
        height: 8,
        decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
          boxShadow: [
            BoxShadow(
                color: color.withValues(alpha: 0.6),
                blurRadius: 6),
          ],
        ),
      ),
    );
  }
}
