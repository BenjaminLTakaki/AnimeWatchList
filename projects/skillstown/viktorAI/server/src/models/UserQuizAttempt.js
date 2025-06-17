const mongoose = require('mongoose');
const { v4: uuidv4 } = require('uuid');

const userAnswerSchema = new mongoose.Schema({
  questionId: {
    type: String,
    ref: 'Question',
    required: true
  },
  userAnswer: {
    type: String,
    required: true
  },
  isCorrect: {
    type: Boolean,
    required: true
  }
});

const userQuizAttemptSchema = new mongoose.Schema({
  _id: {
    type: String,
    default: uuidv4,
    required: true,
  },
  userId: {
    type: String,
    ref: 'User',
    required: true
  },
  quizId: {
    type: String,
    ref: 'Quiz',
    required: true
  },
  answers: [userAnswerSchema],
  score: {
    type: Number,
    required: true,
    default: 0
  },
  feedback_areasForImprovement: {
    type: String,
    required: false
  },
  feedback_strengths: {
    type: String,
    required: false
  },
  completed: {
    type: Boolean,
    default: false
  },
  startTime: {
    type: Date,
    default: Date.now
  },
  endTime: {
    type: Date
  }
}, { timestamps: true });

const UserQuizAttempt = mongoose.model('UserQuizAttempt', userQuizAttemptSchema);

module.exports = UserQuizAttempt; 