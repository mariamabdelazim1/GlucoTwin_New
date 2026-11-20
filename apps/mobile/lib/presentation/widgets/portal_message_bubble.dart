import 'package:flutter/material.dart';

import '../../core/constants/app_colors.dart';

class PortalMessageBubble extends StatelessWidget {
  const PortalMessageBubble({
    super.key,
    required this.text,
    required this.outgoing,
  });

  final String text;
  final bool outgoing;

  @override
  Widget build(BuildContext context) => Align(
        alignment: outgoing ? Alignment.centerRight : Alignment.centerLeft,
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: 4),
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: outgoing ? AppColors.portalIceBlue : Colors.white,
            border: Border.all(color: AppColors.portalBorder),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Text(
            text,
            style: const TextStyle(color: AppColors.portalNavy),
          ),
        ),
      );
}
