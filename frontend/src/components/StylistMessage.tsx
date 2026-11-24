import React from "react";
import { StyleProp, TextStyle, View } from "react-native";
import { Txt } from "@/src/components/Typography";
import { fonts, spacing } from "@/src/theme";

/** Render the emphasis and lists used by saved and new stylist replies. */
export default function StylistMessage({ content, style }: { content: string; style?: StyleProp<TextStyle> }) {
  return (
    <View style={{ gap: spacing.md }}>
      {content.split(/\n\s*\n/).filter(Boolean).map((paragraph, index) => (
        <Txt key={index} style={style}>
          {paragraph.replace(/^\s*[-*]\s+/gm, "• ").split(/(\*\*[^*]+\*\*|\*[^*\n]+\*)/g).map((part, partIndex) => {
            if (part.startsWith("**") && part.endsWith("**")) {
              return <Txt key={partIndex} style={{ fontFamily: fonts.displayBold }}>{part.slice(2, -2)}</Txt>;
            }
            if (part.startsWith("*") && part.endsWith("*")) {
              return <Txt key={partIndex} style={{ fontStyle: "italic" }}>{part.slice(1, -1)}</Txt>;
            }
            return part;
          })}
        </Txt>
      ))}
    </View>
  );
}
