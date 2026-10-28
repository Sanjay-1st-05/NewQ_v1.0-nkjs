
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  SafeAreaView,
  ScrollView,
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  StatusBar,
  Alert,
  ActivityIndicator,
  Image,
  Animated,
} from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { THEMES, THEME_STORAGE_KEY } from './src/theme';
import {
  appendHistory,
  clearAllHistory,
  createHistoryEntry,
  loadExamPreference,
  loadHistory,
  MAX_HISTORY,
  HISTORY_KEY,
  persistAttempt,
  saveExamPreference,
} from './src/storage';
import {
  isCloudEnabled,
  ensureSignedIn,
  watchAuth,
} from './src/firebase';
import {
  cloudClearHistory,
  cloudPushEntry,
  cloudSubscribeHistory,
  cloudUpdateAttempt,
} from './src/cloud';
import {
  analyzeNews,
  extractTextFromImage,
  fetchNewsFeed,
} from './src/api';

const SAMPLE = `The Reserve Bank of India announced a new monetary policy framework aimed at maintaining price stability and supporting economic growth. The policy focuses on managing inflation, maintaining adequate liquidity and strengthening financial stability. The Reserve Bank said the new measures would help improve the resilience of India's financial system.`;

const EXAMS = ['UPSC', 'TNPSC', 'SSC', 'Banking', 'Defence'];

// Rotating status shown in the analyzing progress card on the home screen.
const ANALYZE_STEPS = [
  { icon: 'document-text-outline', label: 'Reading the news content…' },
  { icon: 'filter-outline', label: 'Mapping topics and exam relevance…' },
  { icon: 'help-circle-outline', label: 'Drafting exam-style MCQs…' },
  { icon: 'checkmark-done-outline', label: 'Validating against the source…' },
];

// Per-exam card identity for the Select Exam screen (fixed colors follow the
// design-system accent set, not the theme palette).
const EXAM_META = {
  UPSC: {
    icon: 'ribbon-outline',
    tint: '#FFF4E5',
    color: '#F59E0B',
    sub: 'Civil services · policy and institutions',
  },
  TNPSC: {
    icon: 'medal-outline',
    tint: '#FEE2E2',
    color: '#EF4444',
    sub: 'State civil services · Tamil Nadu focus',
  },
  SSC: {
    icon: 'business-outline',
    tint: '#EDE9FE',
    color: '#8B5CF6',
    sub: 'Staff selection · direct fact recall',
  },
  Banking: {
    icon: 'briefcase-outline',
    tint: '#FEF3C7',
    color: '#D97706',
    sub: 'RBI · monetary policy and finance',
  },
  Defence: {
    icon: 'shield-outline',
    tint: '#D1FAE5',
    color: '#059669',
    sub: 'Security, exercises and strategic affairs',
  },
};

const NEWQ_TEXT_LIMIT = 5000;

// Combine a cloud snapshot with locally stored history. Union by id,
// newest first, capped like local storage. Also returns local-only
// entries so callers can push them back to the cloud (offline healing).
async function mergeCloudHistory(cloudItems) {
  const localItems = await loadHistory();
  const cloudIds = new Set(
    (cloudItems || []).map((item) => item?.id).filter(Boolean),
  );
  const seen = new Set();
  const merged = [];

  [...(cloudItems || []), ...localItems].forEach((item) => {
    if (item?.id && !seen.has(item.id)) {
      seen.add(item.id);
      merged.push(item);
    }
  });

  merged.sort((a, b) =>
    String(b.createdAt || '').localeCompare(String(a.createdAt || '')),
  );

  return {
    merged: merged.slice(0, MAX_HISTORY),
    missingFromCloud: localItems.filter(
      (item) => item?.id && !cloudIds.has(item.id),
    ),
  };
}

export default function App() {
  const [exam, setExam] = useState('UPSC');
  const [text, setText] = useState(SAMPLE);
  const [screen, setScreen] = useState('splash');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [answers, setAnswers] = useState({});
  const [extracting, setExtracting] = useState(false);
  const [photoUri, setPhotoUri] = useState(null);
  const [feed, setFeed] = useState(null);
  const [feedLoading, setFeedLoading] = useState(false);
  const [feedError, setFeedError] = useState(null);
  const [selectedArticle, setSelectedArticle] = useState(null);
  const [articleText, setArticleText] = useState('');
  const [history, setHistory] = useState([]);
  const [currentHistoryId, setCurrentHistoryId] = useState(null);
  const [quizScrollRef, setQuizScrollRef] = useState(null);
  const [analyzeStep, setAnalyzeStep] = useState(0);
  const [quizIndex, setQuizIndex] = useState(0);
  const [quizElapsed, setQuizElapsed] = useState(0);
  const quizStartRef = useRef(0);

  // Must match the backend's MAX_IMAGE_BYTES guard.
  const PHOTO_SIZE_LIMIT = 10 * 1024 * 1024;

  // Theme state: 'light' (design-system default) or 'dark' (classic navy).
  const [theme, setTheme] = useState('light');

  // Cloud sync (Firebase anonymous auth + Firestore). Disabled entirely
  // when firebaseConfig.js is empty — the app then runs local-only.
  const [cloudUid, setCloudUid] = useState(null);
  const [cloudStatus, setCloudStatus] = useState(
    isCloudEnabled() ? 'connecting' : 'off',
  );

  useEffect(() => {
    if (!isCloudEnabled()) {
      return undefined;
    }

    return watchAuth(async (uid) => {
      if (uid) {
        setCloudUid(uid);
        setCloudStatus('on');
        return;
      }

      const signedIn = await ensureSignedIn();
      setCloudUid(signedIn);
      setCloudStatus(signedIn ? 'on' : 'error');
    });
  }, []);

  useEffect(() => {
    // Hydrate history from the cloud live snapshot, merged with whatever
    // is stored locally, and push back entries created while offline.
    if (!cloudUid) {
      return undefined;
    }

    const unsubscribe = cloudSubscribeHistory(
      cloudUid,
      async (cloudItems) => {
        if (!Array.isArray(cloudItems)) {
          return;
        }

        try {
          const { merged, missingFromCloud } =
            await mergeCloudHistory(cloudItems);

          setHistory(merged);
          await AsyncStorage.setItem(
            HISTORY_KEY,
            JSON.stringify(merged),
          );

          missingFromCloud.forEach((entry) => {
            cloudPushEntry(cloudUid, entry);
          });
        } catch (error) {
          // Keep local history untouched when the merge fails.
        }
      },
      () => setCloudStatus('error'),
    );

    return () => (typeof unsubscribe === 'function' ? unsubscribe() : null);
  }, [cloudUid]);

  useEffect(() => {
    // Rotate through the analysis steps while a real analysis is running.
    if (!loading) {
      setAnalyzeStep(0);
      return undefined;
    }
    const timer = setInterval(
      () => setAnalyzeStep((step) => (step + 1) % ANALYZE_STEPS.length),
      1400,
    );
    return () => clearInterval(timer);
  }, [loading]);

  useEffect(() => {
    // Splash auto-advances into the main flow after a short beat.
    if (screen !== 'splash') {
      return undefined;
    }
    const timer = setTimeout(() => setScreen('home'), 2600);
    return () => clearTimeout(timer);
  }, [screen]);

  useEffect(() => {
    AsyncStorage.getItem(THEME_STORAGE_KEY)
      .then((stored) => {
        if (stored === 'light' || stored === 'dark') {
          setTheme(stored);
        }
      })
      .catch(() => {});

    loadExamPreference()
      .then((exam) => {
        if (exam) {
          setExam(exam);
        }
      })
      .catch(() => {});
  }, []);

  const toggleTheme = () => {
    setTheme((current) => {
      const next = current === 'dark' ? 'light' : 'dark';
      AsyncStorage.setItem(THEME_STORAGE_KEY, next).catch(() => {});
      return next;
    });
  };

  const changeExam = (nextExam) => {
    setExam(nextExam);
    saveExamPreference(nextExam).catch(() => {});
  };

  const openHistory = () => {
    setScreen('history');
    loadHistory()
      .then(setHistory)
      .catch(() => setHistory([]));
  };

  const openProfile = () => {
    setScreen('profile');
  };

  const reopenHistoryItem = (entry) => {
    if (!entry?.result) {
      return;
    }
    setResult(entry.result);
    setAnswers({});
    setExam(entry.exam || exam);
    setCurrentHistoryId(entry.id);
    setQuizIndex(0);
    setScreen('analysis');
  };

  const eraseAllHistory = () => {
    Alert.alert(
      'Clear history',
      'Remove all saved analyses and attempts?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear',
          style: 'destructive',
          onPress: () => {
            clearAllHistory()
              .then(setHistory)
              .catch(() => {});
            setCurrentHistoryId(null);

            // Mirror the clear to the cloud session collection.
            if (cloudUid) {
              cloudClearHistory(cloudUid);
            }
          },
        },
      ],
    );
  };

  const saveCurrentAttempt = () => {
    if (!currentHistoryId) {
      return;
    }
    const answered = Object.keys(answers).length;

    if (answered === 0) {
      return;
    }

    const attempt = {
      correct: score,
      answered,
      total: questions.length,
      accuracy: questions.length
        ? Math.round((score / questions.length) * 100)
        : 0,
      at: new Date().toISOString(),
    };

    persistAttempt(
      currentHistoryId,
      attempt.correct,
      attempt.answered,
      attempt.total,
    )
      .then(setHistory)
      .catch(() => {});

    // Keep the attempt record in sync with the cloud session document.
    if (cloudUid) {
      cloudUpdateAttempt(cloudUid, currentHistoryId, attempt);
    }
  };

  // Re-assign the module-level palette and rebuild the stylesheet before any
  // child renders, so every screen and helper reads the active theme.
  palette = THEMES[theme];
  styles = buildStyles();

  const questions = result?.questions ?? [];

  const score = useMemo(
    () =>
      questions.reduce(
        (total, question, index) =>
          total + (answers[index] === question.answer ? 1 : 0),
        0,
      ),
    [questions, answers],
  );

  const analyze = async () => {
    if (!text.trim()) {
      Alert.alert(
        'Add some news',
        'Paste a news article before starting the analysis.',
      );
      return;
    }

    if (text.trim().length < 80) {
      Alert.alert(
        'News text is too short',
        'Please enter at least 80 characters of news content.',
      );
      return;
    }

    setLoading(true);

    try {
      const response = await analyzeNews(text, exam, 5);
      setResult(response);
      setAnswers({});

      // Save the session for the History tab.
      try {
        const entry = createHistoryEntry(response, exam);
        const saved = await appendHistory(entry);
        setHistory(saved);
        setCurrentHistoryId(entry.id);

        // Mirror to Firestore when cloud sync is active.
        if (cloudUid) {
          cloudPushEntry(cloudUid, entry);
        }
      } catch (storageError) {
        // History is a convenience feature — analysis continues without it.
      }

      setScreen('analysis');
    } catch (error) {
      Alert.alert(
        'NewQ could not analyze this news',
        error?.message ||
          'Check your connection to the NewQ API and try again.',
      );
    } finally {
      setLoading(false);
    }
  };

  const startNewAnalysis = () => {
    setQuizIndex(0);
    setScreen('home');
  };

  const startQuiz = () => {
    setAnswers({});
    setQuizIndex(0);
    setQuizElapsed(0);
    quizStartRef.current = Date.now();
    setScreen('quiz');
  };

  const nextQuestion = () => {
    if (quizIndex >= questions.length - 1) {
      // Last question — capture the elapsed time and auto-save the attempt.
      const elapsed = quizStartRef.current
        ? Date.now() - quizStartRef.current
        : 0;
      setQuizElapsed(elapsed);
      saveCurrentAttempt();
      setScreen('results');
      return;
    }

    setQuizIndex((index) => index + 1);
    quizScrollRef?.scrollTo({ y: 0, animated: true });
  };

  const retakeQuiz = () => {
    setAnswers({});
    setQuizIndex(0);
    setQuizElapsed(0);
    quizStartRef.current = Date.now();
    setScreen('quiz');
  };

  const selectAnswer = (questionIndex, option) => {
    setAnswers((current) => ({
      ...current,
      [questionIndex]: option,
    }));
  };

  const pickNewsPhoto = async (mode) => {
    if (loading || extracting) {
      return;
    }

    try {
      if (mode === 'camera') {
        const permission =
          await ImagePicker.requestCameraPermissionsAsync();

        if (!permission.granted) {
          Alert.alert(
            'Camera permission needed',
            'Allow NewQ to use your camera to photograph news articles, or choose an image from your gallery instead.',
          );
          return;
        }
      } else {
        // Gallery permission matters on iOS and older Android versions;
        // newer Android devices use the system photo picker instead.
        const permission =
          await ImagePicker.requestMediaLibraryPermissionsAsync();

        if (permission && permission.granted === false) {
          Alert.alert(
            'Gallery permission needed',
            'Allow NewQ to read photos so you can select a news article image.',
          );
          return;
        }
      }

      const pickerOptions = {
        mediaTypes: ['images'],
        quality: 0.8,
        exif: false,
      };

      const result =
        mode === 'camera'
          ? await ImagePicker.launchCameraAsync(pickerOptions)
          : await ImagePicker.launchImageLibraryAsync(pickerOptions);

      // User cancelled the picker — no error is shown.
      if (!result || result.canceled) {
        return;
      }

      const asset = result.assets && result.assets[0];

      if (!asset || !asset.uri) {
        Alert.alert(
          'No image selected',
          'The selected image could not be opened. Please try again.',
        );
        return;
      }

      if (
        typeof asset.fileSize === 'number' &&
        asset.fileSize > PHOTO_SIZE_LIMIT
      ) {
        Alert.alert(
          'Image too large',
          'Choose an image smaller than 10 MB.',
        );
        return;
      }

      setPhotoUri(asset.uri);
      setExtracting(true);

      try {
        const extraction = await extractTextFromImage(asset.uri);

        // Extracted text lands in the SAME editable news field the user
        // already uses for manual input, so review is always possible.
        setText(extraction.text);
        setScreen('home');

        Alert.alert(
          'Text extracted',
          `${extraction.character_count} characters were read from the photo. Review and edit the text below before analyzing.`,
        );
      } catch (error) {
        setPhotoUri(null);
        Alert.alert(
          'NewQ could not read this photo',
          error?.message ||
            'Check your connection to the NewQ API and try again.',
        );
      } finally {
        setExtracting(false);
      }
    } catch (error) {
      setExtracting(false);
      setPhotoUri(null);
      Alert.alert(
        'NewQ could not access the image',
        error?.message || 'Please try again.',
      );
    }
  };

  const loadFeed = async () => {
    if (feedLoading) {
      return;
    }

    setFeedLoading(true);
    setFeedError(null);

    try {
      const data = await fetchNewsFeed();
      setFeed(data);
    } catch (error) {
      setFeedError(
        error?.message || 'Check your connection to the NewQ API.'
      );
    } finally {
      setFeedLoading(false);
    }
  };

  const openNews = () => {
    setScreen('news');
    loadFeed();
  };

  // The analyzed text is exactly what the feed provided (headline plus the
  // feed summary when one exists) — it is shown editable before analysis.
  const openArticle = (item) => {
    setSelectedArticle(item);
    setArticleText(
      item.summary ? `${item.title}. ${item.summary}` : item.title
    );
    setScreen('article');
  };

  const useArticleForAnalysis = () => {
    const content = articleText.trim();

    if (content.length < 80) {
      Alert.alert(
        'Not enough text',
        'This feed item does not contain enough text yet. Add or edit the text below before analyzing.',
      );
      return;
    }

    setText(content);
    setScreen('home');
  };

  const removeSelectedPhoto = () => setPhotoUri(null);

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar
        barStyle={palette.statusBarContent}
        backgroundColor={palette.navy}
      />

      {screen !== 'splash' && (
        <AppHeader
          screen={screen}
          onHome={startNewAnalysis}
          onToggleTheme={toggleTheme}
          isDark={theme === 'dark'}
        />
      )}

      <ScreenTransition key={screen}>

      {/* SPLASH SCREEN */}
      {screen === 'splash' && (
        <View style={styles.splashScreen}>
          <View style={styles.splashLogo}>
            <Ionicons name="book" size={40} color="#FFFFFF" />
          </View>

          <Text style={styles.splashWordmark}>NewQ</Text>

          <Text style={styles.splashTagline}>
            Current Affairs Today.{'\n'}Questions for Tomorrow.
          </Text>

          <SplashLoadBar />
        </View>
      )}

      {/* HOME SCREEN */}
      {screen === 'home' && (
        <ScrollView
          contentContainerStyle={styles.container}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.heroPanel}>
            <View style={styles.eyebrowRow}>
              <View style={styles.liveDot} />
              <Text style={styles.eyebrow}>
                AI-ASSISTED CURRENT AFFAIRS
              </Text>
            </View>

            <Text style={styles.hero}>
              News in.{'\n'}Questions out.
            </Text>

            <Text style={styles.heroSub}>
              Turn daily news into focused exam practice. Analyze relevance,
              discover key topics and test your understanding.
            </Text>

            <View style={styles.heroFoot}>
              <HeroTag icon="newspaper-outline" label="Analyze" />
              <HeroTag icon="sparkles-outline" label="Generate" />
              <HeroTag icon="school-outline" label="Practice" />
            </View>

            <View pointerEvents="none" style={styles.heroOrb} />
          </View>

          <SectionHeading
            kicker="STEP 01"
            title="Choose your examination"
          />

          <Pressable
            onPress={() => setScreen('select')}
            accessibilityRole="button"
            accessibilityLabel={`Change the exam, currently ${exam}`}
            style={({ pressed }) => [
              styles.examSelectRow,
              pressed && styles.buttonPressed,
            ]}
          >
            <View
              style={[
                styles.examSelectIcon,
                { backgroundColor: EXAM_META[exam]?.tint || '#EFF6FF' },
              ]}
            >
              <Ionicons
                name={EXAM_META[exam]?.icon || 'school-outline'}
                size={21}
                color={EXAM_META[exam]?.color || '#2563EB'}
              />
            </View>

            <View style={styles.examSelectCopy}>
              <Text style={styles.examSelectTitle}>{exam}</Text>
              <Text style={styles.examSelectSub}>
                Get questions tailored to your exam
              </Text>
            </View>

            <Ionicons
              name="chevron-forward"
              size={19}
              color={palette.muted}
            />
          </Pressable>

          <View style={styles.sectionRow}>
            <SectionHeading
              kicker="STEP 02"
              title="Add your news"
            />
            <Text style={styles.optionalLabel}>80+ CHARACTERS</Text>
          </View>

          <View style={styles.inputCard}>
            <View style={styles.cardHeader}>
              <View style={styles.iconTile}>
                <Ionicons
                  name="document-text-outline"
                  size={20}
                  color={palette.cyan}
                />
              </View>

              <View style={styles.cardHeaderText}>
                <Text style={styles.cardTitle}>News article</Text>
                <Text style={styles.cardCaption}>
                  Paste an article or current-affairs update
                </Text>
              </View>

              <Pressable
                onPress={() => setText(SAMPLE)}
                hitSlop={8}
                style={styles.sampleButton}
              >
                <Ionicons
                  name="refresh-outline"
                  size={15}
                  color={palette.cyan}
                />
                <Text style={styles.sampleButtonText}>Sample</Text>
              </Pressable>
            </View>

            {/* PHOTO INPUT ACTIONS */}
            <View style={styles.photoActionsRow}>
              <Pressable
                onPress={() => pickNewsPhoto('camera')}
                disabled={extracting || loading}
                accessibilityRole="button"
                accessibilityLabel="Take a photo of a news article"
                style={({ pressed }) => [
                  styles.photoChip,
                  pressed && styles.photoChipPressed,
                  extracting && styles.photoChipBusy,
                ]}
              >
                {extracting ? (
                  <ActivityIndicator size="small" color={palette.cyan} />
                ) : (
                  <Ionicons
                    name="camera-outline"
                    size={14}
                    color={palette.cyan}
                  />
                )}
                <Text style={styles.photoChipText}>
                  {extracting ? 'Reading photo…' : 'Camera'}
                </Text>
              </Pressable>

              <Pressable
                onPress={() => pickNewsPhoto('gallery')}
                disabled={extracting || loading}
                accessibilityRole="button"
                accessibilityLabel="Choose a news article image from your gallery"
                style={({ pressed }) => [
                  styles.photoChip,
                  pressed && styles.photoChipPressed,
                  extracting && styles.photoChipBusy,
                ]}
              >
                <Ionicons
                  name="images-outline"
                  size={14}
                  color={palette.cyan}
                />
                <Text style={styles.photoChipText}>Gallery</Text>
              </Pressable>

              <Text style={styles.photoCaption}>
                Extract text from a photo
              </Text>
            </View>

            {photoUri && !extracting && (
              <View style={styles.photoPreviewCard}>
                <Image
                  source={{ uri: photoUri }}
                  style={styles.photoPreviewImage}
                />

                <View style={styles.photoPreviewCopy}>
                  <Text style={styles.photoPreviewTitle}>
                    Photo selected
                  </Text>
                  <Text style={styles.photoPreviewSub}>
                    Verify and edit the extracted text below.
                  </Text>
                </View>

                <Pressable
                  onPress={() => setPhotoUri(null)}
                  hitSlop={8}
                  accessibilityRole="button"
                  accessibilityLabel="Remove selected photo"
                >
                  <Ionicons
                    name="close-circle"
                    size={20}
                    color={palette.muted}
                  />
                </Pressable>
              </View>
            )}

            <TextInput
              multiline
              value={text}
              onChangeText={setText}
              style={styles.input}
              placeholder="Paste current-affairs news here..."
              placeholderTextColor={palette.muted}
              textAlignVertical="top"
              maxLength={NEWQ_TEXT_LIMIT}
              accessibilityLabel="News article input"
            />

            <View style={styles.inputFooter}>
              <View style={styles.inputFooterLeft}>
                <Ionicons
                  name="text-outline"
                  size={14}
                  color={palette.muted}
                />
                <Text style={styles.helper}>
                  {text.length}/{NEWQ_TEXT_LIMIT}
                </Text>
              </View>

              <Text
                style={[
                  styles.helper,
                  text.trim().length < 80 && styles.helperWarning,
                ]}
              >
                {text.trim().length < 80
                  ? `${80 - text.trim().length} more needed`
                  : 'Ready to analyze'}
              </Text>
            </View>
          </View>

          <Pressable
            onPress={openNews}
            accessibilityRole="button"
            accessibilityLabel="Browse current affairs news feed"
            style={({ pressed }) => [
              styles.newsBrowseButton,
              pressed && styles.buttonPressed,
            ]}
          >
            <Ionicons
              name="newspaper-outline"
              size={16}
              color={palette.cyan}
            />
            <Text style={styles.newsBrowseText}>
              Browse current-affairs news
            </Text>
            <Text style={styles.newsBrowseHint}>RSS</Text>
          </Pressable>

          <Pressable
            onPress={analyze}
            disabled={loading || extracting}
            style={({ pressed }) => [
              styles.primaryButton,
              pressed && styles.buttonPressed,
              (loading || extracting) && styles.buttonDisabled,
            ]}
          >
            {loading || extracting ? (
              <ActivityIndicator color={palette.navy} />
            ) : (
              <Ionicons
                name="sparkles"
                size={20}
                color={palette.navy}
              />
            )}

            <Text style={styles.primaryButtonText}>
              {loading
                ? 'Analyzing your news...'
                : extracting
                  ? 'Recognizing your photo...'
                  : 'Analyze News'}
            </Text>

            {!loading && (
              <Ionicons
                name="arrow-forward"
                size={18}
                color={palette.navy}
              />
            )}
          </Pressable>

          <Text style={styles.privacyNote}>
            <Ionicons
              name="shield-checkmark-outline"
              size={13}
              color={palette.muted}
            />{' '}
            Source-based analysis · Exam-focused practice
          </Text>

          {loading && (
            <View style={styles.analyzingCard}>
              <View style={styles.analyzingIcon}>
                <Ionicons
                  name={ANALYZE_STEPS[analyzeStep].icon}
                  size={21}
                  color={palette.cyan}
                />
              </View>

              <View style={styles.analyzingCopy}>
                <Text style={styles.analyzingTitle}>
                  NewQ is analyzing your news
                </Text>
                <Text style={styles.analyzingStep}>
                  {ANALYZE_STEPS[analyzeStep].label}
                </Text>
              </View>

              {ANALYZE_STEPS.map((step, stepIndex) => (
                <View
                  key={step.label}
                  style={[
                    styles.analyzingDot,
                    stepIndex <= analyzeStep && styles.analyzingDotActive,
                  ]}
                />
              ))}
            </View>
          )}

          <View style={styles.workflowCard}>
            <Text style={styles.workflowTitle}>
              Your NewQ workflow
            </Text>

            <View style={styles.workflowSteps}>
              <WorkflowStep
                number="01"
                title="Analyze"
                description="Read the news"
              />

              <View style={styles.workflowLine} />

              <WorkflowStep
                number="02"
                title="Understand"
                description="Review insights"
              />

              <View style={styles.workflowLine} />

              <WorkflowStep
                number="03"
                title="Practice"
                description="Answer MCQs"
              />
            </View>
          </View>

          <Text style={styles.footerText}>
            NEWQ · NEWS TO KNOWLEDGE
          </Text>
        </ScrollView>
      )}

      {/* SELECT EXAM SCREEN */}
      {screen === 'select' && (
        <ScrollView
          contentContainerStyle={styles.container}
          showsVerticalScrollIndicator={false}
        >
          <BackButton label="Back" onPress={() => setScreen('home')} />

          <View style={styles.pageHeadingRow}>
            <View style={styles.pageHeadingCopy}>
              <Text style={styles.pageKicker}>GET STARTED</Text>
              <Text style={styles.pageTitle}>Choose Your Exam</Text>
              <Text style={styles.pageSub}>
                Get questions tailored to your exam.
              </Text>
            </View>
          </View>

          {EXAMS.map((item) => {
            const selected = exam === item;
            const meta = EXAM_META[item];

            return (
              <Pressable
                key={item}
                onPress={() => {
                  changeExam(item);
                  setScreen('home');
                }}
                accessibilityRole="button"
                accessibilityLabel={`Select ${item} as the exam`}
                style={({ pressed }) => [
                  styles.examCardRow,
                  selected && styles.examCardRowSelected,
                  pressed && styles.buttonPressed,
                ]}
              >
                <View
                  style={[
                    styles.examCardIcon,
                    { backgroundColor: meta.tint },
                  ]}
                >
                  <Ionicons
                    name={meta.icon}
                    size={22}
                    color={meta.color}
                  />
                </View>

                <View style={styles.examCardCopy}>
                  <Text style={styles.examCardTitle}>{item}</Text>
                  <Text style={styles.examCardSub}>{meta.sub}</Text>
                </View>

                {selected ? (
                  <Ionicons
                    name="checkmark-circle"
                    size={21}
                    color={palette.cyan}
                  />
                ) : (
                  <Ionicons
                    name="chevron-forward"
                    size={19}
                    color={palette.muted}
                  />
                )}
              </Pressable>
            );
          })}

          <Text style={styles.footerText}>NEWQ · NEWS TO KNOWLEDGE</Text>
        </ScrollView>
      )}

      {/* ANALYSIS SCREEN */}
      {screen === 'analysis' && result && (
        <ScrollView
          contentContainerStyle={styles.container}
          showsVerticalScrollIndicator={false}
        >
          <BackButton
            label="Back to input"
            onPress={startNewAnalysis}
          />

          <View style={styles.pageHeadingRow}>
            <View style={styles.pageHeadingCopy}>
              <Text style={styles.pageKicker}>YOUR RESULTS</Text>
              <Text style={styles.pageTitle}>News analysis</Text>
              <Text style={styles.pageSub}>
                An exam-focused breakdown of your article.
              </Text>
            </View>

            <View style={styles.resultIcon}>
              <Ionicons
                name="analytics-outline"
                size={25}
                color={palette.cyan}
              />
            </View>
          </View>

          <View style={styles.metricsGrid}>
            <Metric
              label="EXAM"
              value={result.exam || exam}
              icon="school-outline"
            />

            <Metric
              label="SUBJECT"
              value={result.subject || 'General'}
              icon="layers-outline"
            />

            <Metric
              label="RELEVANCE"
              value={result.relevance || 'Not rated'}
              icon="radio-button-on-outline"
              accent
            />

            <Metric
              label="SCORE"
              value={
                Number.isFinite(Number(result.relevance_score))
                  ? Number(result.relevance_score).toFixed(2)
                  : '—'
              }
              icon="speedometer-outline"
            />
          </View>

          <View style={styles.contentCard}>
            <CardLabel
              icon="locate-outline"
              label="MAIN TOPIC"
            />

            <Text style={styles.topicTitle}>
              {result.topic || 'General Current Affairs'}
            </Text>

            <View style={styles.divider} />

            <CardLabel
              icon="reader-outline"
              label="KEY TAKEAWAYS"
            />

            {Array.isArray(result.summary) &&
            result.summary.length > 0 ? (
              result.summary.map((item, index) => (
                <View
                  key={`${index}-${item}`}
                  style={styles.summaryRow}
                >
                  <View style={styles.summaryBullet}>
                    <Text style={styles.summaryBulletText}>
                      {String(index + 1).padStart(2, '0')}
                    </Text>
                  </View>

                  <Text style={styles.summaryText}>{item}</Text>
                </View>
              ))
            ) : (
              <Text style={styles.mutedBody}>
                No summary was returned for this article.
              </Text>
            )}
          </View>

          <View style={styles.contentCard}>
            <CardLabel
              icon="pricetags-outline"
              label="KEYWORDS"
            />

            <View style={styles.tags}>
              {(result.keywords || []).map((keyword, index) => (
                <View
                  style={styles.keywordTag}
                  key={`${keyword}-${index}`}
                >
                  <Text style={styles.keywordText}>{keyword}</Text>
                </View>
              ))}
            </View>

            <View style={styles.divider} />

            <CardLabel
              icon="checkmark-done-outline"
              label="RELEVANCE SIGNALS"
            />

            {(result.signals || []).length > 0 ? (
              result.signals.map((signal, index) => (
                <View
                  style={styles.signalRow}
                  key={`${signal}-${index}`}
                >
                  <Ionicons
                    name="checkmark-circle"
                    size={16}
                    color={palette.cyan}
                  />
                  <Text style={styles.signalText}>{signal}</Text>
                </View>
              ))
            ) : (
              <Text style={styles.mutedBody}>
                No relevance signals were returned.
              </Text>
            )}
          </View>

          <View style={styles.questionPreview}>
            <View style={styles.previewIcon}>
              <Ionicons
                name="help-circle-outline"
                size={22}
                color={palette.cyan}
              />
            </View>

            <View style={styles.previewCopy}>
              <Text style={styles.previewTitle}>
                Practice questions ready
              </Text>
              <Text style={styles.previewSub}>
                {questions.length} question
                {questions.length === 1 ? '' : 's'} generated for{' '}
                {result.exam || exam}.
              </Text>
            </View>

            <Text style={styles.previewCount}>
              {questions.length}
            </Text>
          </View>

          <Pressable
            onPress={startQuiz}
            disabled={questions.length === 0}
            style={({ pressed }) => [
              styles.primaryButton,
              pressed && styles.buttonPressed,
              questions.length === 0 && styles.buttonDisabled,
            ]}
          >
            <Ionicons
              name="play-circle-outline"
              size={21}
              color={palette.navy}
            />

            <Text style={styles.primaryButtonText}>
              Generate Questions
            </Text>

            <Ionicons
              name="arrow-forward"
              size={18}
              color={palette.navy}
            />
          </Pressable>

          <View style={styles.disclaimer}>
            <Ionicons
              name="information-circle-outline"
              size={17}
              color={palette.cyan}
            />
            <Text style={styles.disclaimerText}>
              NewQ prototype: review generated questions and source
              evidence as part of your exam preparation.
            </Text>
          </View>
        </ScrollView>
      )}

      {/* QUIZ SCREEN */}
      {screen === 'quiz' && result && (
        <ScrollView
          contentContainerStyle={styles.container}
          showsVerticalScrollIndicator={false}
          ref={(ref) => setQuizScrollRef(ref)}
        >
          <BackButton
            label="Back to analysis"
            onPress={() => setScreen('analysis')}
          />

          <View style={styles.quizHero}>
            <View style={styles.quizHeroTop}>
              <View style={styles.quizIcon}>
                <Ionicons
                  name="school-outline"
                  size={23}
                  color={palette.cyan}
                />
              </View>

              <View style={styles.quizScorePill}>
                <Text style={styles.quizScorePillText}>
                  {score} / {questions.length} correct
                </Text>
              </View>
            </View>

            <Text style={styles.pageKicker}>KNOWLEDGE CHECK</Text>
            <Text style={styles.quizHeroTitle}>
              Question {quizIndex + 1} of {questions.length}
            </Text>

            <Text style={styles.quizHeroSub}>
              {result.topic || 'Current Affairs'} ·{' '}
              {result.exam || exam}
            </Text>

            <View style={styles.progressTrack}>
              <View
                style={[
                  styles.progressFill,
                  {
                    width: `${
                      questions.length
                        ? (Object.keys(answers).length /
                            questions.length) *
                          100
                        : 0
                    }%`,
                  },
                ]}
              />
            </View>

            <Text style={styles.progressCaption}>
              {Object.keys(answers).length} of {questions.length}{' '}
              answered
            </Text>
          </View>

          {(() => {
            const index = quizIndex;
            const question = questions[index];

            if (!question) {
              return null;
            }

            const selectedAnswer = answers[index];
            const answered = selectedAnswer !== undefined;
            const correct = selectedAnswer === question.answer;

            return (
              <View
                style={styles.questionCard}
                key={question.id ?? `${index}-${question.question}`}
              >
                <View style={styles.questionMeta}>
                  <Text style={styles.questionNumber}>
                    QUESTION {String(index + 1).padStart(2, '0')}
                  </Text>

                  <View
                  style={[
                    styles.difficultyBadge,
                    question.difficulty === 'Easy' && styles.difficultyEasy,
                    question.difficulty === 'Medium' &&
                      styles.difficultyMedium,
                    question.difficulty === 'Hard' && styles.difficultyHard,
                  ]}
                >
                  <Text
                    style={[
                      styles.difficultyText,
                      question.difficulty === 'Easy' &&
                        styles.difficultyTextEasy,
                      question.difficulty === 'Medium' &&
                        styles.difficultyTextMedium,
                      question.difficulty === 'Hard' &&
                        styles.difficultyTextHard,
                    ]}
                  >
                    {question.difficulty ||
                      'Practice'}
                  </Text>
                </View>
                </View>

                <Text style={styles.questionText}>
                  {question.question}
                </Text>

                {(question.options || []).map(
                  (option, optionIndex) => {
                    const selected = selectedAnswer === option;
                    const isCorrect =
                      answered && option === question.answer;
                    const isIncorrectSelected =
                      selected && option !== question.answer;

                    return (
                      <Pressable
                        key={`${index}-${optionIndex}-${option}`}
                        onPress={() => selectAnswer(index, option)}
                        accessibilityRole="radio"
                        accessibilityState={{ selected }}
                        style={({ pressed }) => [
                          styles.answerOption,
                          selected && styles.answerOptionSelected,
                          isCorrect && styles.answerOptionCorrect,
                          isIncorrectSelected &&
                            styles.answerOptionIncorrect,
                          pressed &&
                            !answered &&
                            styles.optionPressed,
                        ]}
                      >
                        <View
                          style={[
                            styles.optionLetter,
                            selected && styles.optionLetterSelected,
                            isCorrect && styles.optionLetterCorrect,
                            isIncorrectSelected &&
                              styles.optionLetterIncorrect,
                          ]}
                        >
                          <Text
                            style={[
                              styles.optionLetterText,
                              (selected || isCorrect) &&
                                styles.optionLetterTextSelected,
                            ]}
                          >
                            {String.fromCharCode(65 + optionIndex)}
                          </Text>
                        </View>

                        <Text style={styles.answerOptionText}>
                          {option}
                        </Text>

                        {isCorrect && (
                          <Ionicons
                            name="checkmark-circle"
                            size={19}
                            color={palette.success}
                          />
                        )}

                        {isIncorrectSelected && (
                          <Ionicons
                            name="close-circle"
                            size={19}
                            color={palette.danger}
                          />
                        )}
                      </Pressable>
                    );
                  },
                )}

                {answered && (
                  <View
                    style={[
                      styles.explanationBox,
                      correct
                        ? styles.explanationCorrect
                        : styles.explanationIncorrect,
                    ]}
                  >
                    <View style={styles.explanationHeading}>
                      <Ionicons
                        name={
                          correct
                            ? 'checkmark-circle'
                            : 'information-circle'
                        }
                        size={17}
                        color={
                          correct ? palette.success : palette.cyan
                        }
                      />

                      <Text
                        style={[
                          styles.explanationTitle,
                          correct
                            ? styles.successText
                            : styles.cyanText,
                        ]}
                      >
                        {correct
                          ? 'Correct answer'
                          : 'Review this answer'}
                      </Text>
                    </View>

                    <Text style={styles.explanationText}>
                      {question.explanation ||
                        `Correct answer: ${question.answer}`}
                    </Text>
                  </View>
                )}
              </View>
            );
          })()}

          {answers[quizIndex] !== undefined && (
            <Pressable
              onPress={nextQuestion}
              accessibilityRole="button"
              accessibilityLabel="Go to the next question"
              style={({ pressed }) => [
                styles.primaryButton,
                pressed && styles.buttonPressed,
              ]}
            >
              <Text style={styles.primaryButtonText}>
                {quizIndex === questions.length - 1
                  ? 'See Results'
                  : 'Next Question'}
              </Text>
              <Ionicons
                name="arrow-forward"
                size={18}
                color={palette.navy}
              />
            </Pressable>
          )}

          {!(
            Object.keys(answers).length > 0
          ) && (
            <Text style={styles.mutedBody}>
              Select an option to reveal the explanation and continue.
            </Text>
          )}

          <Text style={styles.footerText}>
            KEEP LEARNING · KEEP PRACTISING
          </Text>
        </ScrollView>
      )}

      {/* RESULTS SCREEN */}
      {screen === 'results' && result && (
        <ScrollView
          contentContainerStyle={styles.container}
          showsVerticalScrollIndicator={false}
        >
          <BackButton label="Back to quiz" onPress={() => setScreen('quiz')} />

          <View style={styles.resultsHero}>
            <View style={styles.resultsTrophy}>
              <Ionicons name="trophy" size={34} color="#F59E0B" />
            </View>

            <Text style={styles.resultsTitle}>Quiz Completed!</Text>

            <View style={styles.scoreRing}>
              <Svg width={126} height={126} viewBox="0 0 126 126">
                <Circle
                  cx={63}
                  cy={63}
                  r={56}
                  stroke={palette.progressTrack}
                  strokeWidth={9}
                  fill="none"
                />
                <Circle
                  cx={63}
                  cy={63}
                  r={56}
                  stroke={palette.success}
                  strokeWidth={9}
                  fill="none"
                  strokeLinecap="round"
                  strokeDasharray={2 * Math.PI * 56}
                  strokeDashoffset={
                    2 *
                    Math.PI *
                    56 *
                    (questions.length
                      ? 1 - score / questions.length
                      : 1)
                  }
                  transform="rotate(-90 63 63)"
                />
              </Svg>

              <View style={styles.scoreRingCenter}>
                <Text style={styles.scoreRingValue}>
                  {score}/{questions.length}
                </Text>
                <Text style={styles.scoreRingCaption}>Score</Text>
              </View>
            </View>
          </View>

          <View style={styles.contentCard}>
            <CardLabel icon="stats-chart-outline" label="PERFORMANCE" />

            {(() => {
              const accuracy = questions.length
                ? Math.round((score / questions.length) * 100)
                : 0;
              const wrongCount = Object.keys(answers).length - score;
              const minutes = Math.floor(quizElapsed / 60000);
              const seconds = Math.round((quizElapsed % 60000) / 1000);

              return [
                <View style={styles.statRow} key="acc">
                  <Text style={styles.statLabel}>Performance</Text>
                  <Text style={[styles.statValue, styles.successText]}>
                    {accuracy}%
                  </Text>
                </View>,
                <View style={styles.statRow} key="correct">
                  <Text style={styles.statLabel}>Correct Answers</Text>
                  <Text style={styles.statValue}>{score}</Text>
                </View>,
                <View style={styles.statRow} key="wrong">
                  <Text style={styles.statLabel}>Wrong Answers</Text>
                  <Text style={styles.statValue}>
                    {Math.max(0, wrongCount)}
                  </Text>
                </View>,
                <View style={styles.statRow} key="time">
                  <Text style={styles.statLabel}>Time Taken</Text>
                  <Text style={styles.statValue}>
                    {minutes > 0 ? `${minutes} min ` : ''}
                    {seconds} sec
                  </Text>
                </View>,
              ];
            })()}

            <Text style={styles.mutedBody}>
              {result.topic || 'Current Affairs'} ·{' '}
              {result.exam || exam}
            </Text>
          </View>

          <Pressable
            onPress={() => setScreen('explanations')}
            style={({ pressed }) => [
              styles.primaryButton,
              pressed && styles.buttonPressed,
            ]}
          >
            <Ionicons name="book-outline" size={19} color={palette.navy} />
            <Text style={styles.primaryButtonText}>
              View Explanations
            </Text>
          </Pressable>

          <Pressable
            onPress={retakeQuiz}
            style={({ pressed }) => [
              styles.outlineButton,
              styles.outlineWide,
              pressed && styles.buttonPressed,
            ]}
          >
            <Ionicons
              name="refresh-outline"
              size={16}
              color={palette.text}
            />
            <Text style={styles.outlineButtonText}>Try again</Text>
          </Pressable>

          <Pressable
            onPress={startNewAnalysis}
            style={({ pressed }) => [
              styles.outlineButton,
              styles.outlineWide,
              pressed && styles.buttonPressed,
            ]}
          >
            <Ionicons
              name="newspaper-outline"
              size={16}
              color={palette.text}
            />
            <Text style={styles.outlineButtonText}>
              Try Another News
            </Text>
          </Pressable>

          <Text style={styles.footerText}>
            KEEP LEARNING · KEEP PRACTISING
          </Text>
        </ScrollView>
      )}

      {/* EXPLANATIONS SCREEN */}
      {screen === 'explanations' && result && (
        <ScrollView
          contentContainerStyle={styles.container}
          showsVerticalScrollIndicator={false}
        >
          <BackButton
            label="Back to results"
            onPress={() => setScreen('results')}
          />

          <View style={styles.pageHeadingRow}>
            <View style={styles.pageHeadingCopy}>
              <Text style={styles.pageKicker}>LEARN MORE</Text>
              <Text style={styles.pageTitle}>Detailed Explanation</Text>
              <Text style={styles.pageSub}>
                Every question with the correct answer, reasoning and
                evidence.
              </Text>
            </View>

            <View style={styles.resultIcon}>
              <Ionicons
                name="bulb-outline"
                size={25}
                color={palette.cyan}
              />
            </View>
          </View>

          {questions.map((question, index) => (
            <View
              style={styles.contentCard}
              key={question.id ?? `${index}-${question.question}`}
            >
              <View style={styles.questionMeta}>
                <Text style={styles.questionNumber}>
                  QUESTION {String(index + 1).padStart(2, '0')}
                </Text>

                <View style={styles.difficultyBadge}>
                  <Text style={styles.difficultyText}>
                    {question.difficulty || 'Practice'}
                  </Text>
                </View>
              </View>

              <Text style={styles.questionText}>{question.question}</Text>

              {(question.options || []).map((option, optionIndex) => {
                const correctOption = option === question.answer;

                return (
                  <View
                    style={[
                      styles.answerOption,
                      correctOption && styles.answerOptionCorrect,
                    ]}
                    key={`${index}-${optionIndex}-${option}`}
                  >
                    <View
                      style={[
                        styles.optionLetter,
                        correctOption && styles.optionLetterCorrect,
                      ]}
                    >
                      <Text
                        style={[
                          styles.optionLetterText,
                          correctOption && styles.optionLetterTextSelected,
                        ]}
                      >
                        {String.fromCharCode(65 + optionIndex)}
                      </Text>
                    </View>

                    <Text style={styles.answerOptionText}>{option}</Text>

                    {correctOption && (
                      <Ionicons
                        name="checkmark-circle"
                        size={19}
                        color={palette.success}
                      />
                    )}
                  </View>
                );
              })}

              <View style={[styles.explanationBox, styles.explanationCorrect]}>
                <View style={styles.explanationHeading}>
                  <Ionicons
                    name="checkmark-circle"
                    size={17}
                    color={palette.success}
                  />

                  <Text style={[styles.explanationTitle, styles.successText]}>
                    Correct Answer:{' '}
                    {(question.options || []).indexOf(question.answer) >= 0
                      ? String.fromCharCode(
                          65 + (question.options || []).indexOf(question.answer),
                        )
                      : question.answer}
                  </Text>
                </View>

                <Text style={styles.explanationText}>
                  {question.explanation ||
                    `Correct answer: ${question.answer}`}
                </Text>
              </View>

              {question.source && (
                <View style={styles.explanationSourceRow}>
                  <Ionicons
                    name="quote-outline"
                    size={13}
                    color={palette.muted}
                  />
                  <Text style={styles.explanationSourceText}>
                    {question.source}
                  </Text>
                </View>
              )}
            </View>
          ))}

          <Text style={styles.footerText}>NEWQ · NEWS TO KNOWLEDGE</Text>
        </ScrollView>
      )}

      {/* NEWS FEED SCREEN */}
      {screen === 'news' && (
        <ScrollView
          contentContainerStyle={styles.container}
          showsVerticalScrollIndicator={false}
        >
          <BackButton label="Back to input" onPress={() => setScreen('home')} />

          <View style={styles.pageHeadingRow}>
            <View style={styles.pageHeadingCopy}>
              <Text style={styles.pageKicker}>RSS · CURRENT AFFAIRS</Text>
              <Text style={styles.pageTitle}>News feed</Text>
              <Text style={styles.pageSub}>
                Pick a headline to review its text before analysis.
              </Text>
            </View>

            <Pressable
              onPress={loadFeed}
              disabled={feedLoading}
              accessibilityRole="button"
              accessibilityLabel="Refresh news feed"
              style={({ pressed }) => [
                styles.feedRefreshButton,
                pressed && styles.buttonPressed,
                feedLoading && styles.buttonDisabled,
              ]}
            >
              <Ionicons
                name="refresh-outline"
                size={15}
                color={palette.cyan}
              />
              <Text style={styles.feedRefreshText}>Refresh</Text>
            </Pressable>
          </View>

          {feedLoading && (
            <View style={styles.feedStateCard}>
              <ActivityIndicator color={palette.cyan} />
              <Text style={styles.feedStateText}>Loading news feed…</Text>
            </View>
          )}

          {!feedLoading && feedError && (
            <View style={styles.feedStateCard}>
              <Ionicons name="cloud-offline-outline" size={22} color={palette.danger} />
              <Text style={[styles.feedStateText, styles.feedErrorText]}>
                {feedError}
              </Text>
              <Pressable
                onPress={loadFeed}
                style={styles.feedRetryButton}
                accessibilityLabel="Retry news feed"
              >
                <Text style={styles.feedRetryText}>Try again</Text>
              </Pressable>
            </View>
          )}

          {!feedLoading && !feedError && feed && feed.items.length === 0 && (
            <View style={styles.feedStateCard}>
              <Ionicons name="newspaper-outline" size={22} color={palette.muted} />
              <Text style={styles.feedStateText}>
                No news items are available right now. Try refreshing later.
              </Text>
            </View>
          )}

          {!feedLoading && !feedError && feed && feed.items.length > 0 && (
            <>
              {((feed.feeds && feed.feeds.filter((f) => f.ok).length) || 0) < 1 && (
                <View style={styles.feedStateCard}>
                  <Text style={styles.feedStateText}>
                    Some sources were unavailable, but items were still loaded.
                  </Text>
                </View>
              )}

              {feed.items.map((item, index) => (
                <Pressable
                  key={`${item.source}-${index}-${item.title.slice(0, 24)}`}
                  onPress={() => openArticle(item)}
                  accessibilityRole="button"
                  accessibilityLabel={`Open article: ${item.title}`}
                  style={({ pressed }) => [
                    styles.newsItemCard,
                    pressed && styles.buttonPressed,
                  ]}
                >
                  <View style={styles.newsItemMeta}>
                    <Text style={styles.newsItemSource}>{item.source}</Text>
                    {item.published ? (
                      <Text style={styles.newsItemDate}>
                        {formatFeedDate(item.published)}
                      </Text>
                    ) : null}
                  </View>

                  <Text style={styles.newsItemTitle} numberOfLines={3}>
                    {item.title}
                  </Text>

                  {item.summary ? (
                    <Text
                      style={styles.newsItemSummary}
                      numberOfLines={3}
                    >
                      {item.summary}
                    </Text>
                  ) : (
                    <Text style={styles.newsItemNoSummary}>
                      Headline only · no summary from this source
                    </Text>
                  )}
                </Pressable>
              ))}
            </>
          )}

          <Text style={styles.footerText}>NEWQ · NEWS TO KNOWLEDGE</Text>
        </ScrollView>
      )}

      {/* ARTICLE REVIEW SCREEN */}
      {screen === 'article' && selectedArticle && (
        <ScrollView
          contentContainerStyle={styles.container}
          showsVerticalScrollIndicator={false}
        >
          <BackButton label="Back to news" onPress={() => setScreen('news')} />

          <View style={styles.pageHeadingRow}>
            <View style={styles.pageHeadingCopy}>
              <Text style={styles.pageKicker}>REVIEW BEFORE ANALYSIS</Text>
              <Text style={styles.articleTitle}>{selectedArticle.title}</Text>
            </View>

            <View style={styles.resultIcon}>
              <Ionicons
                name="reader-outline"
                size={25}
                color={palette.cyan}
              />
            </View>
          </View>

          <View style={styles.articleMetaRow}>
            <View style={styles.keywordTag}>
              <Text style={styles.keywordText}>
                {selectedArticle.source}
              </Text>
            </View>
            {selectedArticle.published ? (
              <Text style={styles.articleMetaDate}>
                {formatFeedDate(selectedArticle.published)}
              </Text>
            ) : null}
          </View>

          {!selectedArticle.summary && (
            <Text style={styles.headlineOnlyNote}>
              This feed item includes only a headline — no summary was
              published. Add context by editing the text below, or analyze the
              headline text as it is.
            </Text>
          )}

          <View style={styles.inputCard}>
            <View style={styles.cardHeader}>
              <View style={styles.iconTile}>
                <Ionicons
                  name="document-text-outline"
                  size={20}
                  color={palette.cyan}
                />
              </View>

              <View style={styles.cardHeaderText}>
                <Text style={styles.cardTitle}>Text for analysis</Text>
                <Text style={styles.cardCaption}>
                  Review and edit exactly what will be analyzed
                </Text>
              </View>
            </View>

            <TextInput
              multiline
              value={articleText}
              onChangeText={setArticleText}
              style={styles.input}
              placeholder="Article text will appear here..."
              placeholderTextColor={palette.muted}
              textAlignVertical="top"
              accessibilityLabel="Editable article text for analysis"
            />
          </View>

          <Pressable
            onPress={useArticleForAnalysis}
            accessibilityRole="button"
            accessibilityLabel="Use this article text for analysis"
            style={({ pressed }) => [
              styles.primaryButton,
              pressed && styles.buttonPressed,
            ]}
          >
            <Ionicons
              name="sparkles"
              size={20}
              color={palette.navy}
            />
            <Text style={styles.primaryButtonText}>
              Use this text for analysis
            </Text>
            <Ionicons
              name="arrow-forward"
              size={18}
              color={palette.navy}
            />
          </Pressable>

          <Text style={styles.disclaimerTextAlt}>
            NewQ analyzes only the text shown above, exactly as provided by the
            feed.
          </Text>

          <Text style={styles.footerText}>NEWQ · NEWS TO KNOWLEDGE</Text>
        </ScrollView>
      )}

      {/* HISTORY SCREEN */}
      {screen === 'history' && (
        <ScrollView
          contentContainerStyle={styles.container}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.pageHeadingRow}>
            <View style={styles.pageHeadingCopy}>
              <Text style={styles.pageKicker}>YOUR LIBRARY</Text>
              <Text style={styles.pageTitle}>History</Text>
              <Text style={styles.pageSub}>
                Past analyses and practice attempts, stored on this device.
              </Text>
            </View>

            {history.length > 0 && (
              <Pressable
                onPress={eraseAllHistory}
                accessibilityRole="button"
                accessibilityLabel="Clear all history"
                style={({ pressed }) => [
                  styles.feedRefreshButton,
                  pressed && styles.buttonPressed,
                ]}
              >
                <Ionicons
                  name="trash-outline"
                  size={15}
                  color={palette.danger}
                />
                <Text style={[styles.feedRefreshText, styles.historyClearText]}>
                  Clear
                </Text>
              </Pressable>
            )}
          </View>

          {history.length === 0 && (
            <View style={styles.feedStateCard}>
              <Ionicons name="time-outline" size={22} color={palette.muted} />
              <Text style={styles.feedStateText}>
                No saved analyses yet. Analyze a news article and it will appear
                here.
              </Text>
            </View>
          )}

          {history.map((entry) => (
            <Pressable
              key={entry.id}
              onPress={() => reopenHistoryItem(entry)}
              accessibilityRole="button"
              accessibilityLabel={`Reopen analysis: ${entry.topic}`}
              style={({ pressed }) => [
                styles.newsItemCard,
                pressed && styles.buttonPressed,
              ]}
            >
              <View style={styles.newsItemMeta}>
                <Text style={styles.newsItemSource}>
                  {entry.subject} · {entry.exam}
                </Text>
                <Text style={styles.newsItemDate}>
                  {entry.createdAt
                    ? formatFeedDate(entry.createdAt)
                    : ''}
                </Text>
              </View>

              <Text style={styles.newsItemTitle} numberOfLines={2}>
                {entry.topic}
              </Text>

              {entry.attempt ? (
                <View style={styles.historyAttemptRow}>
                  <Ionicons
                    name="trophy-outline"
                    size={13}
                    color={palette.success}
                  />
                  <Text style={styles.historyAttemptText}>
                    Score {entry.attempt.correct}/{entry.attempt.total} ·{' '}
                    {entry.attempt.accuracy}% accuracy
                  </Text>
                </View>
              ) : (
                <Text style={styles.newsItemNoSummary}>
                  {entry.questionCount} question
                  {entry.questionCount === 1 ? '' : 's'} generated · not yet
                  practiced
                </Text>
              )}
            </Pressable>
          ))}

          <Text style={styles.footerText}>KEEP LEARNING · KEEP PRACTISING</Text>
        </ScrollView>
      )}

      {/* PROFILE SCREEN */}
      {screen === 'profile' && (
        <ScrollView
          contentContainerStyle={styles.container}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.pageHeadingRow}>
            <View style={styles.pageHeadingCopy}>
              <Text style={styles.pageKicker}>SETTINGS</Text>
              <Text style={styles.pageTitle}>Profile</Text>
              <Text style={styles.pageSub}>
                Exam preferences and appearance for this device.
              </Text>
            </View>

            <View style={styles.resultIcon}>
              <Ionicons
                name="person-outline"
                size={25}
                color={palette.cyan}
              />
            </View>
          </View>

          <View style={styles.contentCard}>
            <CardLabel icon="school-outline" label="DEFAULT EXAMINATION" />

            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.examList}
            >
              {EXAMS.map((item) => {
                const selected = exam === item;

                return (
                  <Pressable
                    key={item}
                    onPress={() => changeExam(item)}
                    accessibilityRole="button"
                    accessibilityLabel={`Set default exam to ${item}`}
                    style={[
                      styles.examChip,
                      selected && styles.examChipSelected,
                    ]}
                  >
                    {selected && (
                      <Ionicons
                        name="checkmark-circle"
                        size={15}
                        color={palette.navy}
                      />
                    )}
                    <Text
                      style={[
                        styles.examChipText,
                        selected && styles.examChipTextSelected,
                      ]}
                    >
                      {item}
                    </Text>
                  </Pressable>
                );
              })}
            </ScrollView>

            <Text style={styles.mutedBody}>
              Applies when you open NewQ next time.
            </Text>
          </View>

          <View style={styles.contentCard}>
            <CardLabel icon="contrast-outline" label="APPEARANCE" />

            <View style={styles.profileToggleRow}>
              {[
                ['dark', 'Dark'],
                ['light', 'Light'],
              ].map(([value, label]) => {
                const selected = theme === value;

                return (
                  <Pressable
                    key={value}
                    onPress={() => {
                      if (theme !== value) {
                        toggleTheme();
                      }
                    }}
                    accessibilityRole="radio"
                    accessibilityState={{ selected }}
                    style={[
                      styles.profileOption,
                      selected && styles.profileOptionSelected,
                    ]}
                  >
                    <Ionicons
                      name={value === 'dark' ? 'moon-outline' : 'sunny-outline'}
                      size={14}
                      color={selected ? palette.navy : palette.muted}
                    />
                    <Text
                      style={[
                        styles.examChipText,
                        selected && styles.examChipTextSelected,
                      ]}
                    >
                      {label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </View>

          <View style={styles.contentCard}>
            <CardLabel icon="cloudy-outline" label="NEWQ CLOUD" />

            <View style={styles.profileCloudRow}>
              <View
                style={[
                  styles.profileCloudDot,
                  cloudStatus === 'on' && styles.profileCloudDotOn,
                  cloudStatus === 'connecting' &&
                    styles.profileCloudDotConnecting,
                  (cloudStatus === 'off' || cloudStatus === 'error') &&
                    styles.profileCloudDotOff,
                ]}
              />

              <Text style={styles.profileApiText}>
                {cloudStatus === 'on' &&
                  'Syncing · signed in anonymously'}
                {cloudStatus === 'connecting' && 'Connecting…'}
                {cloudStatus === 'off' && 'Cloud off · local device only'}
                {cloudStatus === 'error' &&
                  'Sign-in failed · using this device only'}
              </Text>
            </View>

            <Text style={styles.mutedBody}>
              {cloudStatus === 'on'
                ? 'History and quiz attempts sync securely across your devices.'
                : 'Add a Firebase project in src/firebaseConfig.js to enable sync.'}
            </Text>
          </View>

          <View style={styles.contentCard}>
            <CardLabel icon="information-circle-outline" label="ABOUT" />
            <Text style={styles.profileApiText}>NewQ mobile v0.1.0</Text>
            <Text style={styles.mutedBody}>
              News in. Questions out. Current-affairs prototype.
            </Text>
          </View>

          <Text style={styles.footerText}>NEWQ · NEWS TO KNOWLEDGE</Text>
        </ScrollView>
      )}
      </ScreenTransition>

      {screen === 'home' ||
      screen === 'select' ||
      screen === 'history' ||
      screen === 'profile' ? (
        <BottomNav
          screen={screen}
          onHome={() => setScreen('home')}
          onHistory={openHistory}
          onProfile={openProfile}
        />
      ) : null}
    </SafeAreaView>
  );
}

// Active theme palette and stylesheet. Both are re-assigned inside the App
// render pass before any child component renders, so all screens and helper
// components always read values for the currently selected theme.
let palette = THEMES.dark;
let styles = null;

const MONTH_ABBREVIATIONS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

function formatFeedDate(isoString) {
  if (!isoString) {
    return '';
  }

  const date = new Date(isoString);

  if (Number.isNaN(date.getTime())) {
    return '';
  }

  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');

  return `${date.getDate()} ${MONTH_ABBREVIATIONS[date.getMonth()]} · ${hours}:${minutes}`;
}

function AppHeader({ screen, onHome, onToggleTheme, isDark }) {
  return (
    <View style={styles.header}>
      <Pressable
        onPress={onHome}
        style={styles.brandArea}
        accessibilityRole="button"
        accessibilityLabel="NewQ home"
      >
        <View style={styles.logo}>
          <Ionicons
            name="flash"
            size={22}
            color={palette.navy}
          />
        </View>

        <View>
          <Text style={styles.brand}>
            NewQ<Text style={styles.brandDot}>.</Text>
          </Text>
          <Text style={styles.brandTag}>
            NEWS TO KNOWLEDGE
          </Text>
        </View>
      </Pressable>

      <View style={styles.headerRight}>
        <Pressable
          onPress={onToggleTheme}
          hitSlop={8}
          accessibilityRole="button"
          accessibilityLabel={
            isDark ? 'Switch to light theme' : 'Switch to dark theme'
          }
          style={styles.themeToggle}
        >
          <Ionicons
            name={isDark ? 'sunny-outline' : 'moon-outline'}
            size={15}
            color={palette.cyan}
          />
        </Pressable>

        <View style={styles.statusDot} />
        <Text style={styles.headerStatus}>
          {screen === 'home'
            ? 'READY'
            : screen === 'select'
              ? 'EXAM'
              : screen === 'news'
                ? 'NEWS'
                : screen === 'article'
                  ? 'ARTICLE'
                  : screen === 'history'
                    ? 'HISTORY'
                    : screen === 'profile'
                      ? 'PROFILE'
                      : screen === 'analysis'
                        ? 'INSIGHTS'
                        : screen === 'results'
                          ? 'RESULTS'
                          : screen === 'explanations'
                            ? 'EXPLANATIONS'
                            : 'PRACTICE'}
        </Text>
      </View>
    </View>
  );
}

function HeroTag({ icon, label }) {
  return (
    <View style={styles.heroTag}>
      <Ionicons
        name={icon}
        size={14}
        color={palette.cyan}
      />
      <Text style={styles.heroTagText}>{label}</Text>
    </View>
  );
}

function SectionHeading({ kicker, title }) {
  return (
    <View style={styles.sectionHeading}>
      <Text style={styles.sectionKicker}>{kicker}</Text>
      <Text style={styles.sectionTitle}>{title}</Text>
    </View>
  );
}

function WorkflowStep({ number, title, description }) {
  return (
    <View style={styles.workflowStep}>
      <Text style={styles.workflowNumber}>{number}</Text>
      <Text style={styles.workflowStepTitle}>{title}</Text>
      <Text style={styles.workflowDescription}>
        {description}
      </Text>
    </View>
  );
}

function BackButton({ label, onPress }) {
  return (
    <Pressable onPress={onPress} style={styles.backButton}>
      <Ionicons
        name="arrow-back"
        size={17}
        color={palette.cyan}
      />
      <Text style={styles.backButtonText}>{label}</Text>
    </Pressable>
  );
}

function Metric({ label, value, icon, accent }) {
  return (
    <View style={styles.metricCard}>
      <View style={styles.metricTop}>
        <Ionicons
          name={icon}
          size={16}
          color={accent ? palette.cyan : palette.muted}
        />
        <Text style={styles.metricLabel}>{label}</Text>
      </View>

      <Text
        style={[
          styles.metricValue,
          accent && styles.metricAccent,
        ]}
        numberOfLines={2}
      >
        {String(value ?? '—')}
      </Text>
    </View>
  );
}

function CardLabel({ icon, label }) {
  return (
    <View style={styles.cardLabelRow}>
      <Ionicons
        name={icon}
        size={15}
        color={palette.cyan}
      />
      <Text style={styles.cardLabel}>{label}</Text>
    </View>
  );
}

function ScreenTransition({ children }) {
  // Fresh Animated.Value per mount: the keyed usage in App remounts this on
  // every screen change, producing a short fade-in for each new screen.
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(opacity, {
      toValue: 1,
      duration: 200,
      useNativeDriver: true,
    }).start();
  }, [opacity]);

  return (
    <Animated.View style={styles.screenTransition}>
      {children}
    </Animated.View>
  );
}

function SplashLoadBar() {
  // Self-contained progress bar shown under the splash tagline.
  const progress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(progress, {
      toValue: 1,
      duration: 2400,
      useNativeDriver: false,
    }).start();
  }, [progress]);

  return (
    <View style={styles.splashLoadTrack}>
      <Animated.View
        style={[
          styles.splashLoadFill,
          {
            width: progress.interpolate({
              inputRange: [0, 1],
              outputRange: ['14%', '82%'],
            }),
          },
        ]}
      />
    </View>
  );
}

function BottomNav({ screen, onHome, onHistory, onProfile }) {
  const tabs = [
    {
      id: 'home',
      label: 'Home',
      icon: screen === 'home' ? 'home' : 'home-outline',
      onPress: onHome,
    },
    {
      id: 'history',
      label: 'History',
      icon: screen === 'history' ? 'time' : 'time-outline',
      onPress: onHistory,
    },
    {
      id: 'profile',
      label: 'Profile',
      icon: screen === 'profile' ? 'person' : 'person-outline',
      onPress: onProfile,
    },
  ];

  return (
    <View style={styles.bottomNav}>
      {tabs.map((tab) => {
        const active = screen === tab.id;

        return (
          <Pressable
            key={tab.id}
            onPress={tab.onPress}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            accessibilityLabel={`${tab.label} tab`}
            style={styles.navItem}
          >
            <Ionicons
              name={tab.icon}
              size={20}
              color={active ? palette.cyan : palette.muted}
            />
            <Text
              style={[
                styles.navLabel,
                active && styles.navLabelActive,
              ]}
            >
              {tab.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const buildStyles = () => StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: palette.navy,
  },
  header: {
    minHeight: 76,
    paddingHorizontal: 20,
    paddingVertical: 12,
    backgroundColor: palette.navy,
    borderBottomWidth: 1,
    borderBottomColor: palette.headerBorder,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  brandArea: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 11,
  },
  logo: {
    width: 42,
    height: 42,
    borderRadius: 14,
    backgroundColor: palette.cyan,
    alignItems: 'center',
    justifyContent: 'center',
  },
  brand: {
    color: palette.text,
    fontSize: 23,
    fontWeight: '900',
    letterSpacing: -0.7,
  },
  brandDot: {
    color: palette.cyan,
  },
  brandTag: {
    color: palette.muted,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 1.6,
    marginTop: 1,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    backgroundColor: palette.surface,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: palette.border,
  },
  themeToggle: {
    width: 26,
    height: 26,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: palette.accentBorder,
    backgroundColor: palette.cyanSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: palette.success,
  },
  headerStatus: {
    color: palette.textSoft,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1.1,
  },
  container: {
    padding: 19,
    paddingBottom: 36,
    backgroundColor: palette.navy,
    flexGrow: 1,
  },
  heroPanel: {
    backgroundColor: palette.navySoft,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: palette.border,
    padding: 21,
    marginBottom: 27,
    overflow: 'hidden',
  },
  eyebrowRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 15,
  },
  liveDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: palette.cyan,
  },
  eyebrow: {
    color: palette.cyan,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1.3,
  },
  hero: {
    color: palette.text,
    fontSize: 37,
    lineHeight: 42,
    fontWeight: '900',
    letterSpacing: -1.3,
  },
  heroSub: {
    color: palette.textSoft,
    fontSize: 13,
    lineHeight: 21,
    marginTop: 12,
    maxWidth: 330,
  },
  heroFoot: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 19,
  },
  heroTag: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: palette.surfaceRaised,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  heroTagText: {
    color: palette.textSoft,
    fontSize: 10,
    fontWeight: '700',
  },
  heroOrb: {
    position: 'absolute',
    width: 120,
    height: 120,
    borderRadius: 60,
    borderWidth: 22,
    borderColor: palette.orb,
    right: -55,
    top: -52,
    opacity: 0.7,
  },
  sectionHeading: {
    marginBottom: 11,
    flexShrink: 1,
  },
  sectionKicker: {
    color: palette.cyan,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 1.4,
    marginBottom: 4,
  },
  sectionTitle: {
    color: palette.text,
    fontSize: 16,
    fontWeight: '800',
    letterSpacing: -0.2,
  },
  examList: {
    paddingBottom: 6,
    gap: 8,
    marginBottom: 19,
  },
  examChip: {
    minHeight: 40,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 15,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surface,
  },
  examChipSelected: {
    backgroundColor: palette.cyan,
    borderColor: palette.cyan,
  },
  examChipText: {
    color: palette.textSoft,
    fontSize: 12,
    fontWeight: '800',
  },
  examChipTextSelected: {
    color: palette.navy,
  },
  sectionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 8,
  },
  optionalLabel: {
    color: palette.muted,
    fontSize: 8,
    fontWeight: '800',
    letterSpacing: 0.8,
    marginTop: 4,
  },
  inputCard: {
    backgroundColor: palette.surface,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 18,
    padding: 15,
    marginBottom: 14,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
  },
  iconTile: {
    width: 39,
    height: 39,
    borderRadius: 12,
    backgroundColor: palette.cyanSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardHeaderText: {
    flex: 1,
  },
  cardTitle: {
    color: palette.text,
    fontSize: 14,
    fontWeight: '800',
  },
  cardCaption: {
    color: palette.muted,
    fontSize: 10,
    marginTop: 3,
  },
  sampleButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderRadius: 9,
    borderWidth: 1,
    borderColor: palette.border,
    paddingHorizontal: 8,
    paddingVertical: 7,
  },
  sampleButtonText: {
    color: palette.cyan,
    fontSize: 10,
    fontWeight: '800',
  },
  photoActionsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 10,
  },
  photoChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: 9,
    borderWidth: 1,
    borderColor: palette.border,
    paddingHorizontal: 10,
    paddingVertical: 8,
    minHeight: 32,
  },
  photoChipPressed: {
    opacity: 0.75,
    backgroundColor: palette.surfaceRaised,
  },
  photoChipBusy: {
    opacity: 0.65,
  },
  photoChipText: {
    color: palette.cyan,
    fontSize: 10,
    fontWeight: '800',
  },
  photoCaption: {
    color: palette.muted,
    fontSize: 9,
    fontWeight: '600',
    marginLeft: 2,
  },
  photoPreviewCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: palette.surfaceDeep,
    borderWidth: 1,
    borderColor: palette.fieldBorder,
    borderRadius: 12,
    padding: 10,
    marginBottom: 10,
  },
  photoPreviewImage: {
    width: 64,
    height: 64,
    borderRadius: 9,
    backgroundColor: palette.surface,
  },
  photoPreviewCopy: {
    flex: 1,
  },
  photoPreviewTitle: {
    color: palette.text,
    fontSize: 12,
    fontWeight: '800',
  },
  photoPreviewSub: {
    color: palette.muted,
    fontSize: 10,
    lineHeight: 15,
    marginTop: 3,
  },
  newsBrowseButton: {
    minHeight: 46,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surface,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    paddingHorizontal: 14,
    marginTop: 2,
    marginBottom: 12,
  },
  newsBrowseText: {
    flex: 1,
    color: palette.text,
    fontSize: 12,
    fontWeight: '800',
  },
  newsBrowseHint: {
    color: palette.muted,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 1.2,
    backgroundColor: palette.surfaceRaised,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 4,
    overflow: 'hidden',
  },
  feedRefreshButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surface,
    paddingHorizontal: 11,
    paddingVertical: 9,
    borderRadius: 11,
  },
  feedRefreshText: {
    color: palette.cyan,
    fontSize: 10,
    fontWeight: '800',
  },
  feedStateCard: {
    alignItems: 'center',
    gap: 9,
    backgroundColor: palette.surface,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 15,
    padding: 18,
    marginBottom: 12,
  },
  feedStateText: {
    color: palette.textSoft,
    fontSize: 12,
    lineHeight: 18,
    textAlign: 'center',
  },
  feedErrorText: {
    color: palette.danger,
  },
  feedRetryButton: {
    marginTop: 2,
    borderWidth: 1,
    borderColor: palette.danger,
    borderRadius: 9,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  feedRetryText: {
    color: palette.danger,
    fontSize: 11,
    fontWeight: '800',
  },
  newsItemCard: {
    backgroundColor: palette.surface,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 15,
    padding: 14,
    marginBottom: 10,
  },
  newsItemMeta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
    marginBottom: 7,
  },
  newsItemSource: {
    color: palette.cyan,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.8,
  },
  newsItemDate: {
    color: palette.muted,
    fontSize: 9,
    fontWeight: '600',
  },
  newsItemTitle: {
    color: palette.text,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '800',
  },
  newsItemSummary: {
    color: palette.textSoft,
    fontSize: 11,
    lineHeight: 17,
    marginTop: 6,
  },
  newsItemNoSummary: {
    color: palette.muted,
    fontSize: 10,
    fontStyle: 'italic',
    marginTop: 6,
  },
  articleTitle: {
    color: palette.text,
    fontSize: 21,
    lineHeight: 27,
    fontWeight: '900',
    letterSpacing: -0.4,
  },
  articleMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 14,
  },
  articleMetaDate: {
    color: palette.muted,
    fontSize: 10,
    fontWeight: '600',
  },
  headlineOnlyNote: {
    color: palette.warning,
    fontSize: 11,
    lineHeight: 17,
    marginBottom: 12,
  },
  disclaimerTextAlt: {
    color: palette.muted,
    fontSize: 10,
    lineHeight: 16,
    textAlign: 'center',
    marginTop: 12,
  },
  bottomNav: {
    flexDirection: 'row',
    borderTopWidth: 1,
    borderTopColor: palette.headerBorder,
    backgroundColor: palette.surface,
    paddingVertical: 10,
    paddingHorizontal: 18,
    gap: 6,
  },
  screenTransition: {
    flex: 1,
  },
  splashScreen: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
    gap: 6,
  },
  splashLogo: {
    width: 96,
    height: 96,
    borderRadius: 28,
    backgroundColor: '#2563EB',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 14,
  },
  splashWordmark: {
    color: '#2563EB',
    fontSize: 34,
    fontWeight: '900',
  },
  splashTagline: {
    color: palette.muted,
    fontSize: 14,
    lineHeight: 22,
    textAlign: 'center',
  },
  splashLoadTrack: {
    width: 170,
    height: 5,
    borderRadius: 3,
    backgroundColor: palette.progressTrack,
    overflow: 'hidden',
    marginTop: 22,
  },
  splashLoadFill: {
    height: '100%',
    borderRadius: 3,
    backgroundColor: '#2563EB',
  },
  examSelectRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: palette.surface,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 16,
    padding: 14,
  },
  examSelectIcon: {
    width: 46,
    height: 46,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },
  examSelectCopy: {
    flex: 1,
    gap: 2,
  },
  examSelectTitle: {
    color: palette.text,
    fontSize: 15,
    fontWeight: '800',
  },
  examSelectSub: {
    color: palette.muted,
    fontSize: 11,
  },
  examCardRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 13,
    backgroundColor: palette.surface,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 16,
    padding: 14,
    minHeight: 68,
  },
  examCardRowSelected: {
    borderColor: palette.cyan,
    backgroundColor: palette.cyanSoft,
  },
  examCardIcon: {
    width: 46,
    height: 46,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },
  examCardCopy: {
    flex: 1,
    gap: 2,
  },
  examCardTitle: {
    color: palette.text,
    fontSize: 15,
    fontWeight: '800',
  },
  examCardSub: {
    color: palette.muted,
    fontSize: 11,
  },
  resultsHero: {
    alignItems: 'center',
    gap: 12,
    paddingVertical: 6,
  },
  resultsTrophy: {
    width: 68,
    height: 68,
    borderRadius: 34,
    backgroundColor: '#FFF4E5',
    alignItems: 'center',
    justifyContent: 'center',
  },
  resultsTitle: {
    color: palette.text,
    fontSize: 20,
    fontWeight: '900',
  },
  scoreRing: {
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 4,
  },
  scoreRingCenter: {
    position: 'absolute',
    alignItems: 'center',
  },
  scoreRingValue: {
    color: palette.text,
    fontSize: 21,
    fontWeight: '900',
  },
  scoreRingCaption: {
    color: palette.muted,
    fontSize: 10,
    fontWeight: '700',
  },
  statRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 7,
  },
  statLabel: {
    color: palette.muted,
    fontSize: 12,
    fontWeight: '600',
  },
  statValue: {
    color: palette.text,
    fontSize: 13,
    fontWeight: '800',
  },
  outlineWide: {
    alignSelf: 'stretch',
    justifyContent: 'center',
  },
  explanationSourceRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 7,
    marginTop: 10,
    padding: 10,
    borderRadius: 10,
    backgroundColor: palette.surfaceRaised,
  },
  explanationSourceText: {
    flex: 1,
    color: palette.muted,
    fontSize: 10.5,
    fontStyle: 'italic',
    lineHeight: 15,
  },
  analyzingCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: palette.surface,
    borderWidth: 1,
    borderColor: palette.accentBorder,
    borderRadius: 16,
    padding: 14,
    marginTop: 14,
  },
  analyzingIcon: {
    width: 42,
    height: 42,
    borderRadius: 12,
    backgroundColor: palette.surfaceRaised,
    alignItems: 'center',
    justifyContent: 'center',
  },
  analyzingCopy: {
    flex: 1,
    gap: 2,
  },
  analyzingTitle: {
    color: palette.text,
    fontSize: 12,
    fontWeight: '800',
  },
  analyzingStep: {
    color: palette.muted,
    fontSize: 11,
  },
  analyzingDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: palette.border,
    marginLeft: 4,
  },
  analyzingDotActive: {
    backgroundColor: palette.cyan,
  },
  navItem: {
    flex: 1,
    alignItems: 'center',
    gap: 3,
    paddingVertical: 4,
    minHeight: 44,
    justifyContent: 'center',
  },
  navLabel: {
    color: palette.muted,
    fontSize: 10,
    fontWeight: '700',
  },
  navLabelActive: {
    color: palette.cyan,
    fontWeight: '900',
  },
  historyClearText: {
    color: palette.danger,
  },
  historyAttemptRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 6,
  },
  historyAttemptText: {
    color: palette.success,
    fontSize: 10,
    fontWeight: '700',
  },
  profileToggleRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 4,
  },
  profileOption: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    minHeight: 40,
    paddingHorizontal: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surface,
  },
  profileOptionSelected: {
    backgroundColor: palette.cyan,
    borderColor: palette.cyan,
  },
  profileApiText: {
    color: palette.text,
    fontSize: 13,
    fontWeight: '800',
    marginBottom: 4,
  },
  profileCloudRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  profileCloudDot: {
    width: 9,
    height: 9,
    borderRadius: 5,
    backgroundColor: palette.muted,
  },
  profileCloudDotOn: {
    backgroundColor: palette.success,
  },
  profileCloudDotConnecting: {
    backgroundColor: palette.warning,
  },
  profileCloudDotOff: {
    backgroundColor: palette.border,
  },
  input: {
    minHeight: 170,
    color: palette.text,
    fontSize: 13,
    lineHeight: 21,
    textAlignVertical: 'top',
    backgroundColor: palette.surfaceDeep,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: palette.fieldBorder,
    padding: 12,
  },
  inputFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 10,
  },
  inputFooterLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  helper: {
    color: palette.muted,
    fontSize: 9,
    fontWeight: '600',
  },
  helperWarning: {
    color: palette.warning,
  },
  primaryButton: {
    minHeight: 54,
    borderRadius: 15,
    backgroundColor: palette.cyan,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingHorizontal: 16,
    marginTop: 2,
  },
  primaryButtonText: {
    color: palette.navy,
    fontSize: 14,
    fontWeight: '900',
    flex: 1,
    textAlign: 'center',
  },
  buttonPressed: {
    opacity: 0.86,
    transform: [{ scale: 0.99 }],
  },
  buttonDisabled: {
    opacity: 0.55,
  },
  privacyNote: {
    color: palette.muted,
    fontSize: 9,
    textAlign: 'center',
    marginTop: 11,
  },
  workflowCard: {
    marginTop: 23,
    backgroundColor: palette.navySoft,
    borderRadius: 17,
    borderWidth: 1,
    borderColor: palette.border,
    padding: 15,
  },
  workflowTitle: {
    color: palette.text,
    fontSize: 12,
    fontWeight: '800',
    marginBottom: 16,
  },
  workflowSteps: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  workflowStep: {
    flex: 1,
  },
  workflowNumber: {
    color: palette.cyan,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1,
  },
  workflowStepTitle: {
    color: palette.text,
    fontSize: 11,
    fontWeight: '800',
    marginTop: 6,
  },
  workflowDescription: {
    color: palette.muted,
    fontSize: 9,
    marginTop: 4,
  },
  workflowLine: {
    height: 1,
    backgroundColor: palette.border,
    width: 16,
    marginTop: 5,
    marginHorizontal: 4,
  },
  footerText: {
    color: palette.footerText,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 1.8,
    textAlign: 'center',
    marginTop: 25,
  },
  backButton: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surface,
    paddingHorizontal: 11,
    paddingVertical: 9,
    borderRadius: 11,
    marginBottom: 20,
  },
  backButtonText: {
    color: palette.textSoft,
    fontSize: 11,
    fontWeight: '800',
  },
  pageHeadingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
    marginBottom: 18,
  },
  pageHeadingCopy: {
    flex: 1,
  },
  pageKicker: {
    color: palette.cyan,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 1.5,
    marginBottom: 6,
  },
  pageTitle: {
    color: palette.text,
    fontSize: 29,
    fontWeight: '900',
    letterSpacing: -0.8,
  },
  pageSub: {
    color: palette.muted,
    fontSize: 12,
    lineHeight: 18,
    marginTop: 5,
  },
  resultIcon: {
    width: 52,
    height: 52,
    borderRadius: 16,
    backgroundColor: palette.cyanSoft,
    borderWidth: 1,
    borderColor: palette.accentBorder,
    alignItems: 'center',
    justifyContent: 'center',
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    gap: 9,
    marginBottom: 13,
  },
  metricCard: {
    width: '48%',
    minHeight: 88,
    backgroundColor: palette.surface,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 15,
    padding: 12,
  },
  metricTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  metricLabel: {
    color: palette.muted,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 1,
  },
  metricValue: {
    color: palette.text,
    fontSize: 15,
    fontWeight: '900',
    marginTop: 10,
  },
  metricAccent: {
    color: palette.cyan,
  },
  contentCard: {
    backgroundColor: palette.surface,
    borderRadius: 17,
    borderWidth: 1,
    borderColor: palette.border,
    padding: 16,
    marginBottom: 12,
  },
  cardLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    marginBottom: 10,
  },
  cardLabel: {
    color: palette.muted,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 1.3,
  },
  topicTitle: {
    color: palette.text,
    fontSize: 23,
    lineHeight: 29,
    fontWeight: '900',
    letterSpacing: -0.4,
  },
  divider: {
    height: 1,
    backgroundColor: palette.border,
    marginVertical: 16,
  },
  summaryRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    marginTop: 9,
  },
  summaryBullet: {
    width: 24,
    height: 24,
    borderRadius: 8,
    backgroundColor: palette.cyanSoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  summaryBulletText: {
    color: palette.cyan,
    fontSize: 8,
    fontWeight: '900',
  },
  summaryText: {
    flex: 1,
    color: palette.textSoft,
    fontSize: 12,
    lineHeight: 19,
  },
  mutedBody: {
    color: palette.muted,
    fontSize: 11,
    lineHeight: 17,
  },
  tags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
  },
  keywordTag: {
    backgroundColor: palette.cyanSoft,
    borderWidth: 1,
    borderColor: palette.accentBorder,
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: 9,
  },
  keywordText: {
    color: palette.keywordText,
    fontSize: 10,
    fontWeight: '700',
  },
  signalRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    marginTop: 7,
  },
  signalText: {
    flex: 1,
    color: palette.textSoft,
    fontSize: 11,
    lineHeight: 17,
  },
  questionPreview: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 11,
    backgroundColor: palette.navySoft,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 15,
    padding: 13,
    marginTop: 3,
    marginBottom: 13,
  },
  previewIcon: {
    width: 41,
    height: 41,
    borderRadius: 12,
    backgroundColor: palette.cyanSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  previewCopy: {
    flex: 1,
  },
  previewTitle: {
    color: palette.text,
    fontSize: 12,
    fontWeight: '800',
  },
  previewSub: {
    color: palette.muted,
    fontSize: 10,
    lineHeight: 15,
    marginTop: 4,
  },
  previewCount: {
    color: palette.cyan,
    fontSize: 22,
    fontWeight: '900',
  },
  disclaimer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    backgroundColor: palette.cyanSoft,
    borderRadius: 12,
    padding: 11,
    marginTop: 12,
  },
  disclaimerText: {
    flex: 1,
    color: palette.keywordText,
    fontSize: 10,
    lineHeight: 16,
  },
  quizHero: {
    backgroundColor: palette.navySoft,
    borderRadius: 21,
    borderWidth: 1,
    borderColor: palette.border,
    padding: 18,
    marginBottom: 15,
  },
  quizHeroTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 18,
  },
  quizIcon: {
    width: 43,
    height: 43,
    borderRadius: 13,
    backgroundColor: palette.cyanSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  quizScorePill: {
    backgroundColor: palette.surfaceRaised,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  quizScorePillText: {
    color: palette.textSoft,
    fontSize: 10,
    fontWeight: '800',
  },
  quizHeroTitle: {
    color: palette.text,
    fontSize: 28,
    fontWeight: '900',
    letterSpacing: -0.6,
  },
  quizHeroSub: {
    color: palette.muted,
    fontSize: 11,
    marginTop: 5,
  },
  progressTrack: {
    height: 5,
    backgroundColor: palette.progressTrack,
    borderRadius: 5,
    overflow: 'hidden',
    marginTop: 18,
  },
  progressFill: {
    height: 5,
    backgroundColor: palette.cyan,
    borderRadius: 5,
  },
  progressCaption: {
    color: palette.muted,
    fontSize: 9,
    marginTop: 7,
  },
  questionCard: {
    backgroundColor: palette.surface,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 17,
    padding: 15,
    marginBottom: 12,
  },
  questionMeta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 13,
  },
  questionNumber: {
    color: palette.cyan,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1.1,
  },
  difficultyBadge: {
    backgroundColor: palette.surfaceRaised,
    borderRadius: 7,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  difficultyEasy: {
    backgroundColor: palette.successSoft,
  },
  difficultyMedium: {
    backgroundColor: palette.surfaceRaised,
  },
  difficultyHard: {
    backgroundColor: palette.dangerSoft,
  },
  difficultyText: {
    color: palette.muted,
    fontSize: 9,
    fontWeight: '800',
  },
  difficultyTextEasy: {
    color: palette.success,
  },
  difficultyTextMedium: {
    color: palette.warning,
  },
  difficultyTextHard: {
    color: palette.danger,
  },
  questionText: {
    color: palette.text,
    fontSize: 15,
    lineHeight: 23,
    fontWeight: '800',
    marginBottom: 14,
  },
  answerOption: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 11,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 12,
    marginBottom: 8,
    backgroundColor: palette.optionIdleBg,
  },
  answerOptionSelected: {
    borderColor: palette.cyan,
    backgroundColor: palette.selectedOptionBg,
  },
  answerOptionCorrect: {
    borderColor: palette.successBorder,
    backgroundColor: palette.successSoft,
  },
  answerOptionIncorrect: {
    borderColor: palette.dangerBorder,
    backgroundColor: palette.dangerSoft,
  },
  optionPressed: {
    opacity: 0.82,
  },
  optionLetter: {
    width: 27,
    height: 27,
    borderRadius: 9,
    borderWidth: 1,
    borderColor: palette.fieldBorder,
    alignItems: 'center',
    justifyContent: 'center',
  },
  optionLetterSelected: {
    backgroundColor: palette.cyan,
    borderColor: palette.cyan,
  },
  optionLetterCorrect: {
    backgroundColor: palette.success,
    borderColor: palette.success,
  },
  optionLetterIncorrect: {
    backgroundColor: palette.danger,
    borderColor: palette.danger,
  },
  optionLetterText: {
    color: palette.textSoft,
    fontSize: 10,
    fontWeight: '900',
  },
  optionLetterTextSelected: {
    color: palette.navy,
  },
  answerOptionText: {
    flex: 1,
    color: palette.textSoft,
    fontSize: 11,
    lineHeight: 17,
  },
  explanationBox: {
    borderRadius: 12,
    padding: 11,
    marginTop: 4,
  },
  explanationCorrect: {
    backgroundColor: palette.successSoft,
    borderWidth: 1,
    borderColor: palette.successCardBorder,
  },
  explanationIncorrect: {
    backgroundColor: palette.cyanSoft,
    borderWidth: 1,
    borderColor: palette.accentBorder,
  },
  explanationHeading: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 5,
  },
  explanationTitle: {
    fontSize: 11,
    fontWeight: '900',
  },
  successText: {
    color: palette.success,
  },
  cyanText: {
    color: palette.cyan,
  },
  explanationText: {
    color: palette.textSoft,
    fontSize: 10.5,
    lineHeight: 16,
  },
  finalResultCard: {
    backgroundColor: palette.navySoft,
    borderWidth: 1,
    borderColor: palette.border,
    borderRadius: 21,
    padding: 22,
    alignItems: 'center',
    marginTop: 4,
  },
  finalResultIcon: {
    width: 48,
    height: 48,
    borderRadius: 15,
    backgroundColor: palette.cyanSoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  finalResultLabel: {
    color: palette.muted,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 1.6,
  },
  finalResultScore: {
    color: palette.text,
    fontSize: 44,
    fontWeight: '900',
    marginTop: 5,
  },
  finalResultTotal: {
    color: palette.muted,
    fontSize: 22,
  },
  finalResultAccuracy: {
    color: palette.cyan,
    fontSize: 11,
    fontWeight: '800',
    marginTop: 2,
    marginBottom: 17,
  },
  finalResultActions: {
    flexDirection: 'row',
    gap: 9,
    width: '100%',
  },
  outlineButton: {
    flex: 1,
    minHeight: 43,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderRadius: 11,
    borderWidth: 1,
    borderColor: palette.border,
    paddingHorizontal: 8,
  },
  outlineButtonText: {
    color: palette.text,
    fontSize: 10,
    fontWeight: '800',
  },
  finalPrimaryButton: {
    flex: 1.25,
    minHeight: 43,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderRadius: 11,
    backgroundColor: palette.cyan,
    paddingHorizontal: 8,
  },
  finalPrimaryButtonText: {
    color: palette.navy,
    fontSize: 10,
    fontWeight: '900',
  },
});
