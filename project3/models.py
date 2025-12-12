from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from uuid import uuid4

class Question(BaseModel):
    text: str
    options: List[str]  # [вариант1, вариант2, ...]
    correct_index: int  # 1-based index для соответствия фронтенду

    def is_correct(self, answer_index: int) -> bool:
        return answer_index == self.correct_index

class Topic(BaseModel):
    pk: int
    name: str
    questions: List[Question]

class Player(BaseModel):
    sid: str
    name: str
    score: int = 0
    answered: bool = False
    answer_index: Optional[int] = None


# В models.py
class Topic(BaseModel):
    pk: int
    name: str
    questions: List[Question]
    
    def to_dict(self):
        return {
            "pk": self.pk,
            "name": self.name,
            "questions": [
                {
                    "text": q.text,
                    "options": q.options,
                    "correct_index": q.correct_index
                }
                for q in self.questions
            ]
        }


class Game(BaseModel):
    uid: str
    topic: Topic
    players: List[Player]
    current_question_index: int = 0
    feedback_sent: bool = False
    
    @property
    def current_question(self) -> Optional[Question]:
        if 0 <= self.current_question_index < len(self.topic.questions):
            return self.topic.questions[self.current_question_index]
        return None
    
    @property
    def question_count(self) -> int:
        return max(0, len(self.topic.questions) - self.current_question_index)
    
    def to_dict(self) -> Dict[str, Any]:
        q = self.current_question
        return {
            "uid": self.uid,
            "question_count": self.question_count,
            "current_question": {
                "text": q.text,
                "options": q.options,
            } if q else None,
            "players": [
                {"name": p.name, "score": p.score}
                for p in self.players
            ],
        }
    
    def record_answer(self, sid: str, index: int) -> bool:
        for p in self.players:
            if p.sid == sid:
                p.answer_index = index
                p.answered = True
                return True
        return False
    
    def both_answered(self) -> bool:
        return all(p.answered for p in self.players)
    
    def evaluate_answers(self) -> Dict[str, Any]:
        q = self.current_question
        if not q:
            return {}
        
        feedback = {
            "answer": q.correct_index,  # чтобы фронт подсветил правильный
            "results": []
        }
        
        for p in self.players:
            is_correct = q.is_correct(p.answer_index)
            if is_correct:
                p.score += 1
            feedback["results"].append({
                "name": p.name,
                "is_correct": is_correct,
                "score": p.score,
            })
            # сброс флага
            p.answered = False
            p.answer_index = None
        
        return feedback
    
    def advance(self):
        self.current_question_index += 1
        self.feedback_sent = False