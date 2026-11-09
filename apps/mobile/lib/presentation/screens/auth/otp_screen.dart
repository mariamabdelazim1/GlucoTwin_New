import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/navigation/route_names.dart';
import '../../widgets/common/gradient_button.dart';

class OtpScreen extends StatefulWidget {
  const OtpScreen({super.key});

  @override
  State<OtpScreen> createState() => _OtpScreenState();
}

class _OtpScreenState extends State<OtpScreen> {
  final _controllers = List.generate(6, (_) => TextEditingController());
  final _focusNodes = List.generate(6, (_) => FocusNode());
  bool _loading = false;
  bool _verified = false;

  @override
  void dispose() {
    for (final c in _controllers) c.dispose();
    for (final f in _focusNodes) f.dispose();
    super.dispose();
  }

  void _verify() {
    setState(() => _loading = true);
    Future.delayed(const Duration(milliseconds: 1200), () {
      setState(() {
        _loading = false;
        _verified = true;
      });
      Future.delayed(const Duration(milliseconds: 800), () {
        if (mounted) context.go(RouteNames.home);
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.darkBackground,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_rounded),
          onPressed: () => context.go(RouteNames.login),
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.all(AppSpacing.screenPadding),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 12),
            Container(
              width: 60,
              height: 60,
              decoration: BoxDecoration(
                gradient: const LinearGradient(colors: AppColors.primaryGradient),
                borderRadius: BorderRadius.circular(16),
              ),
              child: const Icon(Icons.verified_user_rounded,
                  color: Colors.white, size: 30),
            ).animate().scale(
                  begin: const Offset(0.5, 0.5),
                  end: const Offset(1.0, 1.0),
                  curve: Curves.easeOutBack,
                ),
            const SizedBox(height: 24),
            const Text(
              'Verify your\nemail',
              style: TextStyle(
                color: AppColors.textPrimaryDark,
                fontSize: 28,
                fontWeight: FontWeight.w800,
                height: 1.2,
              ),
            ).animate(delay: 100.ms).fadeIn().slideY(begin: 0.2, end: 0),
            const SizedBox(height: 10),
            Text(
              'We sent a 6-digit code to your email.\nPlease enter it below.',
              style: const TextStyle(
                color: AppColors.textSecondaryDark,
                fontSize: 15,
                height: 1.5,
              ),
            ).animate(delay: 200.ms).fadeIn(),
            const SizedBox(height: 40),

            // OTP boxes
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: List.generate(6, (i) {
                return _OtpBox(
                  controller: _controllers[i],
                  focusNode: _focusNodes[i],
                  verified: _verified,
                  onChanged: (val) {
                    if (val.isNotEmpty && i < 5) {
                      _focusNodes[i + 1].requestFocus();
                    }
                    if (val.isEmpty && i > 0) {
                      _focusNodes[i - 1].requestFocus();
                    }
                  },
                );
              }),
            ).animate(delay: 300.ms).fadeIn().slideY(begin: 0.3, end: 0),

            const SizedBox(height: 32),

            if (_verified)
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppColors.accentGreen.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(
                      color: AppColors.accentGreen.withOpacity(0.3)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.check_circle_rounded,
                        color: AppColors.accentGreen),
                    const SizedBox(width: 12),
                    const Text(
                      'Email verified successfully!',
                      style: TextStyle(
                        color: AppColors.accentGreen,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ).animate().fadeIn().scale(begin: const Offset(0.9, 0.9), end: const Offset(1, 1))
            else
              GradientButton(
                label: 'Verify Code',
                onPressed: _verify,
                isLoading: _loading,
                icon: Icons.verified_rounded,
              ).animate(delay: 400.ms).fadeIn(),

            const SizedBox(height: 24),

            Center(
              child: TextButton(
                onPressed: () {},
                child: RichText(
                  text: const TextSpan(
                    text: "Didn't receive it? ",
                    style:
                        TextStyle(color: AppColors.textSecondaryDark, fontSize: 14),
                    children: [
                      TextSpan(
                        text: 'Resend Code',
                        style: TextStyle(
                          color: AppColors.primary,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ).animate(delay: 500.ms).fadeIn(),
          ],
        ),
      ),
    );
  }
}

class _OtpBox extends StatelessWidget {
  const _OtpBox({
    required this.controller,
    required this.focusNode,
    required this.onChanged,
    required this.verified,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final ValueChanged<String> onChanged;
  final bool verified;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 46,
      height: 56,
      child: TextField(
        controller: controller,
        focusNode: focusNode,
        textAlign: TextAlign.center,
        maxLength: 1,
        keyboardType: TextInputType.number,
        onChanged: onChanged,
        style: TextStyle(
          color: verified ? AppColors.accentGreen : AppColors.textPrimaryDark,
          fontSize: 22,
          fontWeight: FontWeight.w700,
        ),
        decoration: InputDecoration(
          counterText: '',
          filled: true,
          fillColor: verified
              ? AppColors.accentGreen.withOpacity(0.1)
              : AppColors.darkCard,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(
                color: verified
                    ? AppColors.accentGreen.withOpacity(0.5)
                    : AppColors.darkBorder),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(
                color: verified
                    ? AppColors.accentGreen.withOpacity(0.5)
                    : AppColors.darkBorder),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide:
                const BorderSide(color: AppColors.primary, width: 1.5),
          ),
          contentPadding: EdgeInsets.zero,
        ),
      ),
    );
  }
}
